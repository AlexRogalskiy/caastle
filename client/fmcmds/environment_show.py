import logging
import prettytable
import os
import yaml

from cliff.command import Command
from pydoc import locate

import call_server as server


class EnvironmentShow(Command):
    
    def get_parser(self, prog_name):
        parser = super(EnvironmentShow, self).get_parser(prog_name)

        parser.add_argument('--env-id',
                            dest='env_id',
                            help="Environment id")

        return parser

    def take_action(self, parsed_args):
        env_id = parsed_args.env_id

        response = server.TakeAction().get_environment(env_id)
        print(response)