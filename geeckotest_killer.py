#!/usr/bin/python3

from myutils import openQAHelper


class Killer(openQAHelper):

    def __init__(self):
        super(Killer, self).__init__('killer')

    def kill(self):
        #self.my_osd_groups = [348]
        for groupid in self.my_osd_groups:
            latest_build = self.get_latest_build(groupid)
            self.logger.info('{} is latest build for {}'.format(latest_build, self.get_group_name(groupid)))
            jobs_to_review = self.osd_get_jobs_where(latest_build, groupid, self.SQL_WHERE_RESULTS)
            for job in jobs_to_review:
                bugrefs = self.get_bugrefs(job.id, filter_by_user='geekotest')
                if len(bugrefs) > 0:
                    self.logger.info('job {} has {} bugrefs'.format(job.id, len(bugrefs)))


def main():
    killer = Killer()
    killer.kill()


if __name__ == "__main__":
    main()
