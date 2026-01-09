import subprocess
import configparser
import requests
import psycopg2
import logging
import urllib3
from models import JobSQL
from datetime import datetime, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TaskHelper:

    OPENQA_URL_BASE = "https://openqa.suse.de/"

    def __init__(self, name: str, dryrun: bool, debug: bool = True):
        self.name: str = name
        self.dryrun: bool = dryrun
        self.showsql: bool = False
        self.config = configparser.ConfigParser()
        self.config.read("/etc/review.ini")
        self.logger = logging.getLogger(name)
        log_level = logging.INFO
        if debug:
            log_level = logging.DEBUG
        logging.basicConfig(format="%(levelname)s:%(message)s", level=log_level)
        if self.config.has_section("OSD"):
            self.osd_username = self.config.get("OSD", "username")
            self.osd_password = self.config.get("OSD", "password")
            self.osd_host = self.config.get("OSD", "host")

    def request_get(self, url):
        response = requests.get(url, timeout=200, verify=False)
        response.raise_for_status()
        json = response.json()
        if "error" in json:
            raise RuntimeError(json)
        return json

    def get_latest_build(self, job_group_id) -> str:
        build = "1"
        try:
            group_json = self.request_get(
                f"{TaskHelper.OPENQA_URL_BASE}group_overview/{job_group_id}.json"
            )
            if len(group_json["build_results"]) == 0:
                self.logger.warning(f"No jobs found in {job_group_id}")
                return None
            build = group_json["build_results"][0]["build"]
        except Exception as e:
            self.logger.error("Failed to get build from openQA - %s", e)
        return build

    def shell_exec(self, cmd: str) -> None:
        if self.dryrun:
            self.logger.debug("NOT EXECUTING - %s", cmd)
            return None
        try:
            self.logger.debug(cmd)
            output = subprocess.check_output(cmd, shell=True)
            self.logger.debug(output)
        except subprocess.CalledProcessError:
            self.logger.error("Command died")
        return None

    def add_comment(self, jobid, comment):
        if comment is None:
            raise AttributeError("Comment is not defined")
        self.logger.debug(
            f'Add a comment="{comment}" to {self.OPENQA_URL_BASE}t{jobid}'
        )
        cmd = f"openqa-cli api --host {self.OPENQA_URL_BASE} -X POST jobs/{jobid}/comments text='{comment}'"
        self.shell_exec(cmd)

    def getJobGroupComments(self, jobgroup: int) -> list[str]:
        self.logger.debug("Fetching comments for job group %d ... ", jobgroup)
        resp = self.request_get(
            f"{self.OPENQA_URL_BASE}api/v1/groups/{jobgroup}/comments"
        )
        comments = [c["id"] for c in resp]  # We just need the comment texts
        self.logger.debug("%d comments fetched", len(comments))
        return comments

    def osd_query(self, query: str) -> list:
        if (
            hasattr(self, "osd_username")
            and hasattr(self, "osd_password")
            and hasattr(self, "osd_host")
        ):
            connection = None
            try:
                connection = psycopg2.connect(
                    user=self.osd_username,
                    password=self.osd_password,
                    host=self.osd_host,
                    port="5432",
                    database="openqa",
                )
                cursor = connection.cursor()
                if self.showsql:
                    self.logger.debug(query)
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


class JobsList:

    def __init__(self) -> None:
        self.jobs = []
        self.job_stat = {
            "names": set(),
            "flavors": set(),
            "arches": set(),
            "versions": set(),
            "machines": set(),
        }

    def append(self, job: JobSQL):
        self.job_stat["names"].add(job.name)
        self.job_stat["flavors"].add(job.flavor)
        self.job_stat["arches"].add(job.arch)
        self.job_stat["versions"].add(job.version)
        self.job_stat["machines"].add(job.machine)
        self.jobs.append(job)

    def log(self, logger):
        if len(self.job_stat) > 0:
            logger.info(
                "Return set contains:\n names=%s\nflavors=%s\narches=%s\nversions=%s\nmachines=%s",
                self.job_stat["names"],
                self.job_stat["flavors"],
                self.job_stat["arches"],
                self.job_stat["versions"],
                self.job_stat["machines"],
            )
        else:
            logger.warning("NOTHING WAS FOUND")


class openQAHelper(TaskHelper):

    def __init__(
        self,
        name: str,
        groupid: int,
        not_older_than_weeks: int,
        dryrun: bool,
        debug: bool = True,
    ):
        super(openQAHelper, self).__init__(name, dryrun, debug=debug)
        time_str = str(datetime.now() - timedelta(weeks=not_older_than_weeks))
        self.SQL_WHERE_RESULTS = f" and result in ('failed', 'timeout_exceeded', 'incomplete') and t_created > '{time_str}'::date"
        self.groupid = groupid

    def find_latest_query(self, latest_build: str, job: JobSQL):
        FIND_LATEST = "select max(id) from jobs where  build='{}' and group_id='{}'  and test='{}' and arch='{}' \
        and flavor='{}' and version='{}' and machine='{}';"
        return FIND_LATEST.format(
            latest_build,
            self.groupid,
            job.name,
            job.arch,
            job.flavor,
            job.version,
            job.machine,
        )

    def osd_get_jobs_where(self, latest_build: str) -> list[JobSQL]:
        jobs = JobsList()
        query = f"{JobSQL.SELECT_QUERY} group_id='{self.groupid}' and build='{latest_build}' "
        rezult = self.osd_query(query)
        if rezult:
            for raw_job in rezult:
                sql_job = JobSQL(raw_job)
                rez = self.osd_query(self.find_latest_query(latest_build, sql_job))
                if rez[0][0] == sql_job.id:
                    jobs.append(sql_job)
            jobs.log(self.logger)
        return jobs.jobs

    def osd_get_all_jobs(self, extra_conditions : str = "", display_summary : bool = True) -> list[JobSQL]:
        jobs = JobsList()
        query = f"{JobSQL.SELECT_QUERY} group_id='{self.groupid}' {extra_conditions}"
        rezult = self.osd_query(query)
        if rezult:
            for raw_job in rezult:
                jobs.append(JobSQL(raw_job))
            if display_summary:
                jobs.log(self.logger)
        return jobs.jobs
