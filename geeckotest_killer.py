#!/usr/bin/python3
import argparse
from myutils import openQAHelper
from models import JobSQL



class Killer(openQAHelper):

    def __init__(self, dry_run: bool = False):
        super(Killer, self).__init__('killer')
        self.dry_run = dry_run

    def kill(self):
        for groupid in self.my_osd_groups:
            latest_build = self.get_latest_build(groupid)
            self.logger.info(f'{latest_build} is latest build for {self.get_group_name(groupid)}')
            jobs_to_review = self.osd_get_jobs_where(
                latest_build, groupid, self.SQL_WHERE_RESULTS)
            for job in jobs_to_review:
                bugrefs = self.get_bugrefs(job.id, filter_by_user='geekotest')
                if len(bugrefs) > 0:
                    self.logger.info(f'job {job.id} has {len(bugrefs)} bugrefs')

    def label_by_module(self, module_filter, build, comment):
        if comment is None:
            comment = openQAHelper.SKIP_PATTERN
        for groupid in self.my_osd_groups:
            if build is None:
                latest_build = self.get_latest_build(groupid)
            else:
                latest_build = build
            self.logger.info(f'{latest_build} is latest build for {self.get_group_name(groupid)}')
            jobs_to_review = self.osd_get_jobs_where(
                latest_build, groupid, self.SQL_WHERE_RESULTS)
            for job in jobs_to_review:
                failed_modules = self.get_failed_modules(job.id)
                if module_filter in failed_modules:
                    if self.dry_run:
                        self.logger.info(f'Job {job.id} wont get comment "{comment}" due to dry_run mode')
                    else:
                        self.add_comment(job, comment)

    def get_all_labels(self):
        self.my_osd_groups = [219]
        bugrefs = set()
        for groupid in self.my_osd_groups:
            latest_build = self.get_latest_build(groupid)
            self.logger.info('{} is latest build for {}'.format(
                latest_build, self.get_group_name(groupid)))
            jobs_to_review = self.osd_get_jobs_where(
                latest_build, groupid, self.SQL_WHERE_RESULTS)
            for job in jobs_to_review:
                bugrefs = bugrefs | self.get_bugrefs(job.id)

        if len(bugrefs) == 0:
            self.logger.info('No jobs labeled')
        else:
            for bug in bugrefs:
                self.logger.info(bug)

    def get_jobs_by(self, query, build, delete):
        self.my_osd_groups = [430]
        for groupid in self.my_osd_groups:
            rez = self.osd_get_jobs_where(build, groupid, query)
            ids_list = ""
            for j1 in rez:
                if delete is None:
                    if len(ids_list) == 0:
                        ids_list = str(j1.id)
                    else:
                        ids_list = "{},{}".format(ids_list, j1.id)
                else:
                    cmd = 'openqa-cli api --host {} -X DELETE jobs/{}'.format(
                        self.OPENQA_URL_BASE, j1.id)
                    self.shell_exec(cmd, dryrun=self.dry_run)
            if delete is None:
                self.logger.info(ids_list)

    def sql(self, query, delete, restart, comment):
        rez = self.osd_query(query)
        for j1 in rez:
            if delete:
                cmd = 'openqa-cli api --host {} -X DELETE jobs/{}'.format(
                    self.OPENQA_URL_BASE, j1[0])
                self.shell_exec(cmd, log=True, dryrun=self.dry_run)
            elif restart:
                clone_cmd = '/usr/share/openqa/script/clone_job.pl'
                common_flags = ' --skip-chained-deps --parental-inheritance '
                cmd = '{} {} --within-instance {} {}'.format(
                    clone_cmd, common_flags, self.OPENQA_URL_BASE, j1[0])
                self.shell_exec(cmd, log=True, dryrun=self.dry_run)
            elif comment:
                self.add_comment(JobSQL(j1), comment)
            else:
                self.logger.info(j1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dry_run', action='store_true',
                        help="Fake any calls to openQA with log messages")
    parser.add_argument('-k', '--kill', action='store_true',
                        help="Kill geekotest comments")
    parser.add_argument('-l', '--labelmodule', help="Label failed job")
    parser.add_argument('-g', '--getlabels',
                        action='store_true', help='get list of labels')
    parser.add_argument('-q', '--query', help='return job ids by filter')
    parser.add_argument('-b', '--build', help='openQA build number')
    parser.add_argument('-c', '--comment', help='Insert comment to openQA job')
    parser.add_argument('--delete', action='store_true', help='delete')
    parser.add_argument('--restart', action='store_true', help='restart')
    parser.add_argument('--sql', help='delete')
    parser.add_argument('--groupid', help='hard code group id')
    args = parser.parse_args()
    killer = Killer(args.dry_run)
    if args.groupid:
        killer.my_osd_groups = [args.groupid]
    if args.kill:
        killer.kill()
    elif args.getlabels:
        killer.get_all_labels()
    elif args.labelmodule:
        killer.label_by_module(args.labelmodule, args.build, args.comment)
    elif args.query:
        killer.get_jobs_by(args.query, args.build, args.delete)
    elif args.sql:
        killer.sql(args.sql, args.delete, args.restart, args.comment)


if __name__ == "__main__":
    main()
