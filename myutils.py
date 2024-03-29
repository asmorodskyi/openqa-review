import subprocess
import configparser
import requests
import psycopg2
import logzero
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TaskHelper:

    OPENQA_URL_BASE = 'https://openqa.suse.de/'

    def __init__(self, name: str, dryrun: bool):
        self.name:str = name
        self.dryrun: bool = dryrun
        self.config = configparser.ConfigParser()
        self.config.read('/etc/review.ini')
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
        response = requests.get(url, timeout=200, verify=False).json()
        if 'error' in response:
            raise RuntimeError(response)
        return response

    def get_latest_build(self, job_group_id) -> str:
        build = '1'
        try:
            group_json = self.request_get(f'https://openqa.suse.de/group_overview/{job_group_id}.json')
            if len(group_json['build_results']) == 0:
                self.logger.warning(f"No jobs found in {job_group_id}")
                return None
            build = group_json['build_results'][0]['build']
        except Exception as e:
            self.logger.error("Failed to get build from openQA - %s", e)
        return build

    def shell_exec(self, cmd : str) -> None:
        if self.dryrun:
            self.logger.debug("NOT EXECUTING - %s", cmd)
            return None
        try:
            self.logger.debug(cmd)
            output = subprocess.check_output(cmd, shell=True)
            self.logger.debug(output)
        except subprocess.CalledProcessError:
            self.logger.error('Command died')
        return None

    def add_comment(self, jobid, comment):
        if comment is None:
            raise AttributeError("Comment is not defined")
        self.logger.debug(
            f'Add a comment="{comment}" to {self.OPENQA_URL_BASE}t{jobid}'
        )
        cmd = f"openqa-cli api --host {self.OPENQA_URL_BASE} -X POST jobs/{jobid}/comments text=\'{comment}\'"
        self.shell_exec(cmd)

    def osd_query(self, query: str) -> list:
        if hasattr(self, 'osd_username') and hasattr(self, 'osd_password') and hasattr(self, 'osd_host'):
            connection = None
            try:
                connection = psycopg2.connect(user=self.osd_username, password=self.osd_password,
                                              host=self.osd_host, port="5432", database="openqa")
                cursor = connection.cursor()
                #self.logger.debug(query)
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
