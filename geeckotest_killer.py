#!/usr/bin/python3
import argparse
from myutils import openQAHelper
from models import JobSQL


class Killer(openQAHelper):

    OPENQA_API_BASE = "https://openqa.suse.de/api/v1/"
    # we have job groups which are used for several versions.
    # in such a case current logic may found unnecessary failures
    # related to older versions. To avoid this we limit query by time
    not_older_than_weeks : int = 7

    def __init__(self, groupid: int, dryrun: bool = False, latest_build: str = None):
        super(Killer, self).__init__("killer", groupid, Killer.not_older_than_weeks, dryrun)
        if latest_build is None:
            self.latest_build = self.get_latest_build(self.groupid)
        else:
            self.latest_build = latest_build
        self.logger.info(
            "%s is latest build for %s", self.latest_build, self.get_group_name()
        )

    def get_group_name(self) -> str:
        group_json = self.request_get(
            f"{self.OPENQA_URL_BASE}group_overview/{self.groupid}.json"
        )
        return group_json["group"]["name"]

    def get_bugrefs(self, jobs: "list[JobSQL]", filter_by_user=None):
        bugrefs = set()
        for job in jobs:
            response = self.request_get(f"{self.OPENQA_API_BASE}jobs/{job.id}/comments")
            for comment in response:
                if not filter_by_user or filter_by_user == comment["userName"]:
                    bugrefs |= set(comment["bugrefs"])
        return bugrefs

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

    def label_by_module(self, module_filter, comment):
        jobs_to_review = self.osd_get_jobs_where(self.latest_build)
        for job in jobs_to_review:
            if module_filter in self.get_failed_modules(job.id):
                self.add_comment(job.id, comment)

    def get_all_labels(self):
        jobs_to_review = self.osd_get_jobs_where(self.latest_build)
        # TODO reveal ability to get only comments from certain user
        # bugrefs = self.get_bugrefs(job.id, filter_by_user='geekotest')
        bugrefs = self.get_bugrefs(jobs_to_review)
        if len(bugrefs) == 0:
            self.logger.info("No jobs labeled")
        else:
            for bug in bugrefs:
                self.logger.info(bug)

    def get_jobs_by(self, args):
        rez = self.osd_get_all_jobs(args.query)
        ids_list = ""
        for j1 in rez:
            if args.delete:
                cmd = f"openqa-cli api --host {self.OPENQA_URL_BASE} -X DELETE jobs/{j1.id}"
                self.shell_exec(cmd)
            elif args.restart:
                clone_cmd = "/usr/share/openqa/script/clone_job.pl"
                common_flags = (
                    " --skip-chained-deps --parental-inheritance "
                )
                params_str = ""
                if args.params:
                    params_str = " ".join(args.params)
                cmd = f"{clone_cmd} {common_flags} --within-instance {self.OPENQA_URL_BASE} {j1.id} {params_str}"
                self.shell_exec(cmd)
            elif args.comment:
                self.add_comment(j1.id, args.comment)
            elif args.delete_comment:
                self.delete_comment(j1.id)
            else:
                if len(ids_list) == 0:
                    ids_list = str(j1.id)
                else:
                    ids_list = f"{ids_list},{j1.id}"
        if ids_list is not None:
            self.logger.info(ids_list)

    def delete_comment(self, jobid):
        response = self.request_get(f"{self.OPENQA_API_BASE}jobs/{jobid}/comments")
        if response:
            cmd = f"openqa-cli api --host {self.OPENQA_URL_BASE} -X DELETE /jobs/{jobid}/comments/{response[0]['id']}"
            self.shell_exec(cmd)

    def investigate(self, jobid):
        cmd = f"/usr/share/openqa/script/clone_job.pl --skip-chained-deps --parental-inheritance {jobid} BUILD=INV{jobid} _GROUP=0 --within-instance {self.OPENQA_URL_BASE}"
        variables_set = set()
        response = self.request_get(
            f"{self.OPENQA_URL_BASE}tests/{jobid}/file/vars.json"
        )
        # first collecting ALL _TEST_REPOS variable so later we can reset others when we testing some certain incident
        for var in response:
            if "_TEST_REPOS" in var:
                variables_set.add(var)
        for var in response:
            # if variable exists in set hence matching expected pattern we proceed
            if var in variables_set:
                # we picking incidents one by one and clonning jobs with this single incident and other incidents removed
                i = 1
                for incident in response[var].split(","):
                    test_issues_var = f"{var}={incident} TEST={response['TEST']}{i} "
                    i += 1
                    for empty_var in variables_set:
                        if empty_var != var:
                            test_issues_var = f"{test_issues_var} {empty_var}=''"
                    self.shell_exec(f"{cmd} {test_issues_var}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--dryrun",
        action="store_true",
        help="Fake any calls to openQA with log messages",
    )
    parser.add_argument("-l", "--labelmodule", help="Label failed job")
    parser.add_argument(
        "-g", "--getlabels", action="store_true", help="get list of labels"
    )
    parser.add_argument("-q", "--query", help="return job ids by filter")
    parser.add_argument("-b", "--build", help="openQA build number")
    parser.add_argument("-c", "--comment", help="Insert comment to openQA job")
    parser.add_argument(
        "params", help="extra params added to openQA job", nargs="*", default=[]
    )
    parser.add_argument("--delete", action="store_true", help="delete", default=False)
    parser.add_argument(
        "--delete_comment", action="store_true", help="delete comment", default=False
    )
    parser.add_argument(
        "--investigate", help="Clone aggregate scenario with indiviual incidents"
    )
    parser.add_argument("--restart", action="store_true", help="restart", default=False)
    parser.add_argument("--groupid", help="hard code group id", required=True)
    parser.add_argument(
        "--showsql", action="store_true", help="Show sql", default=False
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="No extra conditions everything is selected",
        default=False,
    )
    args = parser.parse_args()
    killer = Killer(args.groupid, args.dryrun, args.build)
    if args.showsql:
        killer.showsql = True
    if args.getlabels:
        killer.get_all_labels()
    elif args.labelmodule:
        killer.label_by_module(args.labelmodule, args.comment)
    elif args.query or args.all:
        killer.get_jobs_by(args)
    elif args.investigate:
        killer.investigate(args.investigate)


if __name__ == "__main__":
    main()
