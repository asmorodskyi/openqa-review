#!/usr/bin/python3

from bs4 import BeautifulSoup
from myutils import openQAHelper
from urllib.request import urlopen
import re


class ImageUploader(openQAHelper):

    def __init__(self):
        super(ImageUploader, self).__init__('ImageUploader')
        self.url = "https://download.suse.de/ibs/Devel:/PubCloud:/Stable:/CrossCloud:/SLE15-SP3:/ModifiedTestImages/images/"
        self.upload_job_id_query = "select max(id) from jobs where group_id='274'  and test='publiccloud_upload_img' and arch='x86_64' and flavor='EC2';"
        self.clone_job_cmd = "/usr/share/openqa/script/clone_job.pl --skip-chained-deps --parental-inheritance --from https://openqa.suse.de --host http://autobot.qa.suse.de  {} WORKER_CLASS=qemu_x86_64 PUBLIC_CLOUD_IMAGE_LOCATION={}"

    def run(self):
        with urlopen(self.url) as response:
            soup = BeautifulSoup(response.read(), 'html.parser')
            for a in soup.findAll('a', href=True):
                m = re.match(r"\.\/(SLES15-SP3-Lasso-BYOS.x86_64-[\d\.]+-EC2-HVM-Build[\d\.]+raw.xz)$", a['href'])
                if m:
                    full_url = "{}{}".format(self.url, m.group(1))
                    self.logger.info("Will upload {} \n".format(full_url))
                    rez = self.osd_query(self.upload_job_id_query)
                    self.shell_exec(self.clone_job_cmd.format(rez[0][0], full_url), log=True)
                    return 0


def main():
    image_uploader = ImageUploader()
    image_uploader.run()


if __name__ == "__main__":
    main()
