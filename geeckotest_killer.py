#!/usr/bin/python3

from myutils import openQAHelper

import re
import argparse


class Killer(openQAHelper):

    def __init__(self, dry_run: bool = False):
        super(Killer, self).__init__('killer')
        self.dry_run = dry_run

    def kill(self):
        for groupid in self.my_osd_groups:
            latest_build = self.get_latest_build(groupid)
            self.logger.info('{} is latest build for {}'.format(latest_build, self.get_group_name(groupid)))
            jobs_to_review = self.osd_get_jobs_where(latest_build, groupid, self.SQL_WHERE_RESULTS)
            for job in jobs_to_review:
                bugrefs = self.get_bugrefs(job.id, filter_by_user='geekotest')
                if len(bugrefs) > 0:
                    self.logger.info('job {} has {} bugrefs'.format(job.id, len(bugrefs)))

    def label_by_module(self, module_filter):
        self.my_osd_groups = [409]
        for groupid in self.my_osd_groups:
            latest_build = self.get_latest_build(groupid)
            self.logger.info('{} is latest build for {}'.format(latest_build, self.get_group_name(groupid)))
            jobs_to_review = self.osd_get_jobs_where(latest_build, groupid, self.SQL_WHERE_RESULTS)
            for job in jobs_to_review:
                failed_modules = self.get_failed_modules(job.id)
                if module_filter in failed_modules:
                    self.add_comment(job, openQAHelper.SKIP_PATTERN)

    def get_all_labels(self):
        self.my_osd_groups = [219]
        bugrefs = set()
        for groupid in self.my_osd_groups:
            latest_build = self.get_latest_build(groupid)
            self.logger.info('{} is latest build for {}'.format(latest_build, self.get_group_name(groupid)))
            jobs_to_review = self.osd_get_jobs_where(latest_build, groupid, self.SQL_WHERE_RESULTS)
            for job in jobs_to_review:
                bugrefs = bugrefs | self.get_bugrefs(job.id)

        if len(bugrefs) == 0:
            self.logger.info('No jobs labeled')
        else:
            for bug in bugrefs:
                self.logger.info(bug)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dry_run', action='store_true', help="Fake any calls to openQA with log messages")
    parser.add_argument('-k', '--kill', action='store_true', help="Kill geekotest comments")
    parser.add_argument('-l', '--labelmodule', help="Label failed job")
    parser.add_argument('-g', '--getlabels', action='store_true', help='get list of labels')
    args = parser.parse_args()
    killer = Killer(args.dry_run)
    if args.kill:
        killer.kill()
    elif args.getlabels:
        killer.get_all_labels()
    else:
        killer.label_by_module(args.labelmodule)


if __name__ == "__main__":
    main()
