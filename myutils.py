from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import logzero
import smtplib
import socket
import os
import traceback
import requests
import subprocess
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, MessageLatency, JobSQL
import configparser
from datetime import datetime, timedelta
import time
import psycopg2
import webbrowser
import urllib3

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
                name=name, logfile='/var/log/{0}/{0}.log'.format(self.name), formatter=logzero.LogFormatter(
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
            self.logger.error("Fail to send email - {}".format(traceback.format_exc()))

    def handle_error(self, error=''):
        if not error:
            error = traceback.format_exc()
        self.logger.error(error)
        if self.send_mails:
            self.send_mail('[{}] ERROR - {}'.format(self.name, socket.gethostname()), error)

    def get_latest_build(self, job_group_id=262):
        build = '1'
        try:
            group_json = requests.get('https://openqa.suse.de/group_overview/{}.json'.format(job_group_id),
                                      verify=False).json()
            if len(group_json['build_results']) == 0:
                self.logger.warning("No jobs found in {}".format(job_group_id))
                return None
            build = group_json['build_results'][0]['build']
        except Exception as e:
            self.logger.error("Failed to get build from openQA - %s", e)
        finally:
            return build

    def shell_exec(self, cmd, log=False, is_json=False, dryrun: bool = False):
        if dryrun:
            self.logger.info("NOT EXECUTING - {}".format(cmd))
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
        self.SQL_WHERE_RESULTS = " and result in ('failed', 'timeout_exceeded', 'incomplete') and t_created > '{}'::date".format(
            time_str)

    def get_previous_builds(self, job_group_id: int):
        builds = ""
        group_json = requests.get('{}group_overview/{}.json'.format(self.OPENQA_URL_BASE, job_group_id),
                                  verify=False).json()
        max_deep = len(group_json['build_results'])
        # we need maximum 3 builds
        for i in range(0, 3):
            if (i + 1) >= max_deep:
                break
            if not builds:
                builds = "'{}'".format(group_json['build_results'][i + 1]['build'])
            else:
                builds = "{},'{}'".format(builds, group_json['build_results'][i + 1]['build'])
        return builds

    def get_group_name(self, job_group_id: int):
        group_json = requests.get('{}group_overview/{}.json'.format(self.OPENQA_URL_BASE, job_group_id),
                                  verify=False).json()
        return group_json['group']['name']

    def get_comments_from_job(self, job_id):
        response = requests.get('{}jobs/{}/comments'.format(self.OPENQA_API_BASE, job_id), verify=False)
        try:
            if 'error' in response.json():
                raise RuntimeError(response.json())
        except simplejson.errors.JSONDecodeError as e:
            self.logger.error('{} is not JSON. {}'.format(response, e))
        return response.json()

    def comments_has_ignore_label(self, comments):
        for comment in comments:
            if openQAHelper.SKIP_PATTERN in comment['renderedMarkdown']:
                return True
        return False

    def extract_bugrefs_from(self, comments, filter_by_user=None):
        bugrefs = set()
        for comment in comments:
            if not filter_by_user:
                bugrefs |= set(comment['bugrefs'])
            elif filter_by_user == comment['userName']:
                bugrefs |= set(comment['bugrefs'])
        return bugrefs

    def get_bugrefs(self, job_id, filter_by_user=None):
        comments = self.get_comments_from_job(job_id)
        return self.extract_bugrefs_from(comments, filter_by_user)

    def check_latency(self, topic, subject):
        msg = self.msg_query.filter(MessageLatency.topic == topic).filter(
            MessageLatency.subject == subject).one_or_none()
        rez = 0
        if msg:
            if datetime.now() < msg.locked_till:
                self.logger.info('still locked {}'.format(msg))
                rez = 3
            else:
                msg.lock()
                self.logger.info('Got locked {}'.format(msg))
                rez = 2
            msg.inc_cnt()
        else:
            new_msg = MessageLatency(topic, subject)
            self.session.add(new_msg)
            rez = 1
        self.session.commit()
        return rez

    def osd_get_jobs_where(self, build, group_id, extra_conditions=''):
        rezult = self.osd_query("{} build='{}' and group_id='{}' {}".format(
            JobSQL.SELECT_QUERY, build, group_id, extra_conditions))
        jobs = []
        for raw_job in rezult:
            sql_job = JobSQL(raw_job)
            rez = self.osd_query(self.FIND_LATEST.format(
                build, group_id, sql_job.name, sql_job.arch, sql_job.flavor))
            if rez[0][0] == sql_job.id:
                jobs.append(sql_job)
        return jobs

    def osd_get_latest_failures(self, before_hours, group_ids):
        jobs = []
        rezult = self.osd_query("{} result='failed' and t_created > (NOW() - INTERVAL '{} hours' ) and group_id in ({})".format(
            JobSQL.SELECT_QUERY, before_hours, group_ids))
        for raw_job in rezult:
            sql_job = JobSQL(raw_job)
            rez = self.osd_query(self.FIND_LATEST.format(
                sql_job.build, raw_job[7], sql_job.name, sql_job.arch, sql_job.flavor))
            if rez[0][0] == sql_job.id:
                jobs.append(sql_job)
        self.logger.info("Got {} failed jobs in monitored job groups on osd".format(len(rezult)))
        return jobs

    def open_in_browser(self, jobs):
        for job in jobs:
            time.sleep(2)
            webbrowser.get('firefox').open("{}t{}".format(self.OPENQA_URL_BASE, job.id), autoraise=False)

    def osd_job_group_results(self, groupid, build):
        rezult = self.osd_query(
            "select result,count(*) from jobs where group_id={} and build='{}' group by result;".format(groupid, build))
        final_string = ""
        cnt_jobs = 0
        for rez in rezult:
            final_string = "{} {}={}".format(final_string, rez[0], rez[1])
            cnt_jobs += rez[1]
        final_string = "total jobs={} {}".format(cnt_jobs, final_string)
        return final_string

    def get_failed_modules(self, job_id):
        rezult = self.osd_query(
            "select name from job_modules where job_id={} and result='failed'".format(job_id))
        failed_modules = ""
        rezult.sort()
        for rez in rezult:
            if not failed_modules:
                failed_modules = "{}".format(rez[0])
            else:
                failed_modules = "{},{}".format(failed_modules, rez[0])
        if failed_modules:
            return failed_modules
        else:
            return "NULL"

    def add_comment(self, job, comment):
        self.logger.debug('Add a comment to {} with reference {}. {}t{}'.format(
            job, comment, self.OPENQA_URL_BASE, job.id))
        cmd = 'openqa-cli api --host {} -X POST jobs/{}/comments text=\'{}\''.format(self.OPENQA_URL_BASE, job.id,
                                                                                     comment)
        self.shell_exec(cmd, self.dry_run)


def is_matched(rules, topic, msg):
    for rule in rules:
        rkey, filter_matches = rule
        if rkey.match(topic) and filter_matches(topic, msg):
            return True
