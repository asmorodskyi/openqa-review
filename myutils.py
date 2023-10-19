from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import socket
import smtplib
import traceback
import subprocess
import json
import configparser
from datetime import datetime, timedelta
import time
import webbrowser
import requests
import psycopg2
import logzero
import urllib3
from models import JobSQL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TaskHelper:

    def __init__(self, name):
        self.name = name
        self.config = configparser.ConfigParser()
        self.config.read('/etc/review.ini')
        self.to_list = self.config.get('DEFAULT', 'to_list', fallback='asmorodskyi@suse.com')
        self.send_mails = self.config['DEFAULT'].getboolean('send_emails', fallback=True)
        if self.config['DEFAULT'].getboolean('log_to_file', fallback=True):
            self.logger = logzero.setup_logger(
                name=name, logfile=f'/var/log/{self.name}/{self.name}.log', formatter=logzero.LogFormatter(
                    fmt='%(color)s[%(asctime)s %(module)s:%(lineno)d]%(end_color)s %(message)s',
                    datefmt='%d-%m %H:%M:%S'))
        else:
            self.logger = logzero.setup_logger(
                name=name, formatter=logzero.LogFormatter(
                    fmt='%(color)s%(module)s:%(lineno)d|%(end_color)s %(message)s'))
        if self.config.has_section('OSD'):
            self.osd_username = self.config.get('OSD', 'username')
            self.osd_password = self.config.get('OSD', 'password')
            self.osd_host = self.config.get('OSD', 'host')

    def request_get(self, url):
        return requests.get(url, timeout=200, verify=False).json()

    def send_mail(self, subject, message, html_message: str = None, custom_to_list: str = None):
        try:
            if html_message:
                mimetext = MIMEMultipart('alternative')
                part1 = MIMEText(message, 'plain')
                part2 = MIMEText(html_message, 'html')
                mimetext.attach(part1)
                mimetext.attach(part2)
            else:
                mimetext = MIMEText(message)
            mimetext['Subject'] = subject
            mimetext['From'] = 'asmorodskyi@suse.com'
            if not custom_to_list:
                custom_to_list = self.to_list
            mimetext['To'] = custom_to_list
            server = smtplib.SMTP('relay.suse.de', 25)
            server.ehlo()
            server.sendmail('asmorodskyi@suse.com', custom_to_list.split(','), mimetext.as_string())
        except Exception:
            self.logger.error(f"Fail to send email - {traceback.format_exc()}")

    def handle_error(self, error=''):
        if not error:
            error = traceback.format_exc()
        self.logger.error(error)
        if self.send_mails:
            self.send_mail(f'[{self.name}] ERROR - {socket.gethostname()}', error)

    def get_latest_build(self, job_group_id=262):
        build = '1'
        try:
            group_json = self.request_get(f'https://openqa.suse.de/group_overview/{job_group_id}.json')
            if len(group_json['build_results']) == 0:
                self.logger.warning(f"No jobs found in {job_group_id}")
                return None
            build = group_json['build_results'][0]['build']
        except Exception as e:
            self.logger.error("Failed to get build from openQA - %s", e)
        finally:
            return build

    def shell_exec(self, cmd, log=False, is_json=False, dryrun: bool = False):
        if dryrun:
            self.logger.info(f"NOT EXECUTING - {cmd}")
            return
        try:
            if log:
                self.logger.info(cmd)
            output = subprocess.check_output(cmd, shell=True)
            if is_json:
                o_json = json.loads(output)
                if log:
                    self.logger.info("%s", o_json)
                return o_json
            else:
                if log:
                    self.logger.info("%s", output)
                return output
        except subprocess.CalledProcessError:
            self.handle_error('Command died')

    def osd_query(self, query):
        if hasattr(self, 'osd_username') and hasattr(self, 'osd_password') and hasattr(self, 'osd_host'):
            connection = None
            try:
                connection = psycopg2.connect(user=self.osd_username, password=self.osd_password,
                                              host=self.osd_host, port="5432", database="openqa")
                cursor = connection.cursor()
                # self.logger.debug(query)
                cursor.execute(query)
                return cursor.fetchall()
            except (Exception, psycopg2.Error) as error:
                self.logger.error(error)
            finally:
                if connection is not None:
                    cursor.close()
                    connection.close()
        else:
            raise AttributeError("Connection to osd is not defined ")


class openQAHelper(TaskHelper):

    FIND_LATEST = "select max(id) from jobs where  build='{}' and group_id='{}'  and test='{}' and arch='{}' \
        and flavor='{}';"
    OPENQA_URL_BASE = 'https://openqa.suse.de/'
    OPENQA_API_BASE = 'https://openqa.suse.de/api/v1/'
    SKIP_PATTERN = '@reviewed'
    # we have job groups which are used for several versions.
    # in such a case current logic may found unnecessary failures
    # related to older versions. To avoid this we limit query by time
    not_older_than_weeks = 7

    def __init__(self, name, aliasgroups: str = None):
        super(openQAHelper, self).__init__(name)
        if aliasgroups:
            groups_section = 'ALIAS'
            var_name = aliasgroups
        else:
            groups_section = 'DEFAULT'
            var_name = 'groups'
        self.my_osd_groups = [int(num_str) for num_str in str(self.config.get(
            groups_section, var_name, fallback='262,219,274,275')).split(',')]
        time_str = str(datetime.now() - timedelta(weeks=openQAHelper.not_older_than_weeks))
        self.SQL_WHERE_RESULTS = f" and result in ('failed', 'timeout_exceeded', 'incomplete') and t_created > '{time_str}'::date"

    def get_previous_builds(self, job_group_id: int):
        builds = ""
        group_json = self.request_get(f'{self.OPENQA_URL_BASE}group_overview/{job_group_id}.json')
        max_deep = len(group_json['build_results'])
        # we need maximum 3 builds
        for i in range(3):
            if (i + 1) >= max_deep:
                break
            if not builds:
                builds = f"'{group_json['build_results'][i + 1]['build']}'"
            else:
                builds = f"{builds},'{group_json['build_results'][i + 1]['build']}'"
        return builds

    def get_group_name(self, job_group_id: int):
        group_json = self.request_get(f'{self.OPENQA_URL_BASE}group_overview/{job_group_id}.json')
        return group_json['group']['name']

    def get_comments_from_job(self, job_id):
        response = self.request_get(f'{self.OPENQA_API_BASE}jobs/{job_id}/comments')
        if 'error' in response:
            raise RuntimeError(response)
        return response

    def comments_has_ignore_label(self, comments):
        return any(
            openQAHelper.SKIP_PATTERN in comment['renderedMarkdown']
            for comment in comments
        )

    def extract_bugrefs_from(self, comments, filter_by_user=None):
        bugrefs = set()
        for comment in comments:
            if not filter_by_user or filter_by_user == comment['userName']:
                bugrefs |= set(comment['bugrefs'])
        return bugrefs

    def get_bugrefs(self, job_id, filter_by_user=None):
        comments = self.get_comments_from_job(job_id)
        return self.extract_bugrefs_from(comments, filter_by_user)

    def osd_get_jobs_where(self, build, group_id, extra_conditions=''):
        rezult = self.osd_query(f"{JobSQL.SELECT_QUERY} build='{build}' and group_id='{group_id}' {extra_conditions}")
        if rezult is None:
            return None
        jobs = []
        for raw_job in rezult:
            sql_job = JobSQL(raw_job)
            self.logger.info(raw_job)
            rez = self.osd_query(self.FIND_LATEST.format(
                build, group_id, sql_job.name, sql_job.arch, sql_job.flavor))
            if rez[0][0] == sql_job.id:
                jobs.append(sql_job)
        return jobs

    def osd_get_latest_failures(self, before_hours, group_ids):
        jobs = []
        rezult = self.osd_query(f"{JobSQL.SELECT_QUERY} result='failed' and t_created > (NOW() - INTERVAL '{before_hours} hours' ) and group_id in ({group_ids})")
        for raw_job in rezult:
            sql_job = JobSQL(raw_job)
            rez = self.osd_query(self.FIND_LATEST.format(
                sql_job.build, raw_job[7], sql_job.name, sql_job.arch, sql_job.flavor))
            if rez[0][0] == sql_job.id:
                jobs.append(sql_job)
        self.logger.info(f"Got {len(rezult)} failed jobs in monitored job groups on osd")
        return jobs

    def open_in_browser(self, jobs):
        for job in jobs:
            time.sleep(2)
            webbrowser.get('firefox').open(
                f"{self.OPENQA_URL_BASE}t{job.id}", autoraise=False
            )

    def osd_job_group_results(self, groupid, build):
        rezult = self.osd_query(
            f"select result,count(*) from jobs where group_id={groupid} and build='{build}' group by result;"
        )
        final_string = ""
        cnt_jobs = 0
        for rez in rezult:
            final_string = f"{final_string} {rez[0]}={rez[1]}"
            cnt_jobs += rez[1]
        final_string = f"total jobs={cnt_jobs} {final_string}"
        return final_string

    def get_failed_modules(self, job_id):
        rezult = self.osd_query(
            f"select name from job_modules where job_id={job_id} and result='failed'"
        )
        failed_modules = ""
        rezult.sort()
        for rez in rezult:
            if not failed_modules:
                failed_modules = f"{rez[0]}"
            else:
                failed_modules = f"{failed_modules},{rez[0]}"
        return failed_modules or "NULL"

    def add_comment(self, job, comment, dry_run):
        self.logger.debug(
            f'Add a comment to {job} with reference {comment}. {self.OPENQA_URL_BASE}t{job.id}'
        )
        cmd = f"openqa-cli api --host {self.OPENQA_URL_BASE} -X POST jobs/{job.id}/comments text=\'{comment}\'"
        self.shell_exec(cmd, dry_run)


def is_matched(rules, topic, msg):
    for rule in rules:
        rkey, filter_matches = rule
        if rkey.match(topic) and filter_matches(topic, msg):
            return True
