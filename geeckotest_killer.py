#!/usr/bin/python3
import argparse
from myutils import openQAHelper
from models import JobSQL



class Killer(openQAHelper):

    def __init__(self, groupid: str, dryrun: bool = False, latest_build: str = None):
        super(Killer, self).__init__('killer')
        self.dryrun = dryrun
        self.groupid = groupid
        if latest_build is None:
            self.latest_build = self.get_latest_build(self.groupid)
        else:
            self.latest_build = latest_build
        self.logger.info('%s is latest build for %s', self.latest_build, self.get_group_name(self.groupid))

    def label_by_module(self, module_filter, comment):
        if comment is None:
            comment = openQAHelper.SKIP_PATTERN
        jobs_to_review = self.osd_get_jobs_where(self.latest_build, self.groupid, self.SQL_WHERE_RESULTS)
        for job in jobs_to_review:
            if module_filter in self.get_failed_modules(job.id):
                self.add_comment(job, comment, self.dryrun)

    def get_all_labels(self):
        jobs_to_review = self.osd_get_jobs_where(self.latest_build, self.groupid, self.SQL_WHERE_RESULTS)
        bugrefs = set()
        for job in jobs_to_review:
            #TODO reveal ability to get only comments from certain user
            #bugrefs = self.get_bugrefs(job.id, filter_by_user='geekotest')
            bugrefs = bugrefs | self.get_bugrefs(job.id)
        if len(bugrefs) == 0:
            self.logger.info('No jobs labeled')
        else:
            for bug in bugrefs:
                self.logger.info(bug)

    def get_jobs_by(self, query, delete, restart, comment, params):
        rez = self.osd_get_jobs_where(self.latest_build, self.groupid, query)
        ids_list = ""
        for j1 in rez:
            if delete:
                cmd = f'openqa-cli api --host {self.OPENQA_URL_BASE} -X DELETE jobs/{j1.id}'
                self.shell_exec(cmd, log=True, dryrun=self.dryrun)
            elif restart:
                clone_cmd = '/usr/share/openqa/script/clone_job.pl'
                common_flags = ' --skip-chained-deps --parental-inheritance '
                if params is None:
                    params = ''
                cmd = f'{clone_cmd} {common_flags} --within-instance {self.OPENQA_URL_BASE} {j1.id} {params}'
                self.shell_exec(cmd, log=True, dryrun=self.dryrun)
            elif comment:
                self.add_comment(j1, comment, self.dryrun)
            else:
                if len(ids_list) == 0:
                    ids_list = str(j1.id)
                else:
                    ids_list = f"{ids_list},{j1.id}"
        if not delete and not restart and comment is None:
            self.logger.info(ids_list)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dryrun', action='store_true',
                        help="Fake any calls to openQA with log messages")
    parser.add_argument('-l', '--labelmodule', help="Label failed job")
    parser.add_argument('-g', '--getlabels',
                        action='store_true', help='get list of labels')
    parser.add_argument('-q', '--query', help='return job ids by filter')
    parser.add_argument('-b', '--build', help='openQA build number')
    parser.add_argument('-c', '--comment', help='Insert comment to openQA job')
    parser.add_argument('-p', '--params', help='extra params added to openQA job')
    parser.add_argument('--delete', action='store_true', help='delete')
    parser.add_argument('--restart', action='store_true', help='restart')
    parser.add_argument('--groupid', help='hard code group id', required=True)
    args = parser.parse_args()
    killer = Killer(args.groupid, args.dryrun, args.build)
    if args.getlabels:
        killer.get_all_labels()
    elif args.labelmodule:
        killer.label_by_module(args.labelmodule, args.comment)
    elif args.query:
        killer.get_jobs_by(args.query, args.delete, args.restart, args.comment, args.params)


if __name__ == "__main__":
    main()
