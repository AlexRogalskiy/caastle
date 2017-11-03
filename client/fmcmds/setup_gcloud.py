import os

from cliff.command import Command

class GCloudSetup(Command):

    def take_action(self, parsed_args):
        os.system("wget https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-sdk-178.0.0-linux-x86_64.tar.gz")
        os.system("gunzip google-cloud-sdk-178.0.0-linux-x86_64.tar.gz")
        os.system("tar -xvf google-cloud-sdk-178.0.0-linux-x86_64.tar")
        os.system("./google-cloud-sdk/install.sh --quiet")
        os.system("./google-cloud-sdk/bin/gcloud auth login")
        os.system("./google-cloud-sdk/bin/gcloud auth application-default login")