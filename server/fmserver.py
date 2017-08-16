import datetime
import logging
import os
import sys
import tarfile
import time
import thread

from os.path import expanduser

from flask import Flask, jsonify, request
from flask_restful import reqparse, abort, Resource, Api

app = Flask(__name__)
api = Api(app)

parser = reqparse.RequestParser()
parser.add_argument('app_content', location='form')
parser.add_argument('app_name', location='form')

home_dir = expanduser("~")

APP_STORE_PATH = ("{home_dir}/.cld/data/deployments").format(home_dir=home_dir)
ENV_STORE_PATH = APP_STORE_PATH

from common import fm_logger
from common import common_functions
from dbmodule import db_handler
import request_handler
import environment_handler
import app_handler

dbhandler = db_handler.DBHandler()

def start_thread(request_handler_thread):
    try:
        request_handler_thread.run()
    except Exception as e:
        fmlogging.error(e)

class ResourcesResource(Resource):
    def post(self):
        fmlogging.debug("Received POST request to create resource")
        args = request.get_json(force=True)

        response = jsonify()
        response.status_code = 201

        args_dict = dict(args)
        
        try:
            # Handle resource creation request
            if not 'resource_info' in args_dict:
                response.status_code = 400
            else:
                request_obj = args_dict['resource_info']
                resource_id = dbhandler.add_resource(request_obj)
                request_obj['resource_id'] = resource_id
                request_handler_thread = request_handler.RequestHandler(request_obj)
                thread.start_new_thread(start_thread, (request_handler_thread, ))

                response.headers['location'] = ('/resource/{resource_id}').format(resource_id=resource_id)
        except OSError as oe:
            fmlogging.error(oe)
            # Send back internal server error
            response.status_code = 500

        return response

    def get(self):
        fmlogging.debug("Received GET request for all resources.")
        resp_data = {}
        
        env_id = request.args.get('env_id')

        if env_id:
            resp_data['data'] = dbhandler.get_resources_for_environment(env_id)
        else:
            resp_data['data'] = dbhandler.get_resources()

        response = jsonify(**resp_data)
        response.status_code = 200
        return response

class ResourceResource(Resource):
    def get(self, resource_id):
        fmlogging.debug("Received GET request for resource %s" % resource_id)
        resp_data = {}

        env_id = request.args.get('env_id')

        resp_data['data'] = dbhandler.get_resource(resource_id)

        response = jsonify(**resp_data)
        response.status_code = 200
        return response

    def delete(self, resource_id):
        fmlogging.debug("Received DELETE request for resource %s" % resource_id)

        response = jsonify()
        response.status_code = 201
        
        try:
            request_obj = dict()
            resource = db_handler.DBHandler().get_resource(resource_id)
            if resource:
                request_obj['resource_type'] = resource[db_handler.RESOURCE_TYPE]
                request_obj['name'] = resource[db_handler.RESOURCE_NAME]
                request_obj['resource_id'] = resource_id
                request_obj['artifact_type'] = 'resource'
                request_obj['action'] = 'delete'
                request_handler_thread = request_handler.RequestHandler(request_obj)
                thread.start_new_thread(start_thread, (request_handler_thread, ))
                response.headers['location'] = ('/resource/{resource_id}').format(resource_id=resource_id)
            else:
                response.status_code = 404
        except OSError as oe:
            fmlogging.error(oe)
            # Send back service unavailable status
            response.status_code = 503

        return response

class AppsRestResource(Resource):

    def post(self):
        fmlogging.debug("Received POST request to deploy app")
        args = request.get_json(force=True)

        response = jsonify()
        response.status_code = 201

        args_dict = dict(args)

        try:
            if not 'app_info' in args_dict:
                response.status_code = 400
            else:
                app_info = args_dict['app_info']

                env_id = -1
                if 'env_id' in app_info:
                    env_id = app_info['env_id']
                    env_obj = dbhandler.get_environment(app_info['env_id'])
                    if not env_obj[db_handler.ENV_STATUS] or env_obj[db_handler.ENV_STATUS] != 'available':
                        response.status_code = 412
                        response.status_message = 'Environment not ready.'
                        return response
                app_name = app_info['app_name']
                app_tar_name = app_info['app_tar_name']
                content = app_info['app_content']
                cloud = app_info['target']

                app_location, app_version = common_functions.store_app_contents(app_name, app_tar_name, content)
                app_info['app_location'] = app_location
                app_info['app_version'] = app_version
                app_id = dbhandler.add_app(app_name, app_location, app_version, cloud, int(env_id))
                request_handler_thread = app_handler.AppHandler(app_id, app_info, action='deploy')
                thread.start_new_thread(start_thread, (request_handler_thread, ))
                response.headers['location'] = ('/apps/{app_id}').format(app_id=app_id)
        except Exception as e:
            fmlogging.error(e)
            # Send back Internal Server Error
            response.status_code = 500

        return response
    
    def get(self):
        fmlogging.debug("Received GET request for all apps")
        resp_data = {}

        resp_data['data'] = dbhandler.get_apps()

        response = jsonify(**resp_data)
        response.status_code = 200
        return response
    
class AppRestResource(Resource):
    def get(self, app_id):

        resp_data = {}

        resp_data['data'] = dbhandler.get_app(app_id)

        response = jsonify(**resp_data)
        response.status_code = 200
        return response

    def put(self, app_id):
        fmlogging.debug("Received PUT request to redeploy app")

        args = request.get_json(force=True)

        response = jsonify()
        response.status_code = 201

        args_dict = dict(args)
        app_obj = db_handler.DBHandler().get_app(app_id)

        try:
            if not 'app_info' in args_dict:
                response.status_code = 400
            else:
                app_info = args_dict['app_info']
                app_name = app_obj[db_handler.APP_NAME]
                app_tar_name = app_info['app_tar_name']
                content = app_info['app_content']
                app_info['app_name'] = app_name

                cloud = app_obj[db_handler.APP_DEP_TARGET]
                app_info['target'] = cloud
                app_info['env_id'] = app_obj[db_handler.APP_ENV_ID]

                app_location, app_version = common_functions.store_app_contents(app_name, app_tar_name, content)
                app_info['app_location'] = app_location
                app_info['app_version'] = app_version
                request_handler_thread = app_handler.AppHandler(app_id, app_info, action='redeploy')
                thread.start_new_thread(start_thread, (request_handler_thread, ))
                response.headers['location'] = ('/apps/{app_id}').format(app_id=app_id)
        except Exception as e:
            fmlogging.error(e)
            # Send back Internal Server Error
            response.status_code = 500

        return response

    def delete(self, app_id):
        fmlogging.debug("Received DELETE request for app %s" % app_id)
        resp_data = {}

        response = jsonify(**resp_data)
        app_info = {}

        app_obj = db_handler.DBHandler().get_app(app_id)
        if app_obj:
            app_info['target'] = app_obj[db_handler.APP_DEP_TARGET]
            app_info['app_name'] = app_obj[db_handler.APP_NAME]
            app_info['app_location'] = app_obj[db_handler.APP_LOCATION]

            request_handler_thread = app_handler.AppHandler(app_id, app_info, action='delete')
            thread.start_new_thread(start_thread, (request_handler_thread, ))
            response.status_code = 201
        else:
            response.status_code = 404
        return response

class EnvironmentsRestResource(Resource):
    def post(self):
        fmlogging.debug("Received POST request to create environment")
        args = request.get_json(force=True)

        response = jsonify()
        response.status_code = 201

        args_dict = dict(args)

        try:
            # Handle resource creation request
            if not 'environment_def' in args_dict:
                response.status_code = 400
            else:
                environment_def = args_dict['environment_def']
                environment_name = args_dict['environment_name']
                env_version_stamp = common_functions.get_version_stamp()
                env_id = dbhandler.add_environment(environment_name, environment_def, env_version_stamp)
                environment_info = {}
                environment_info['name'] = environment_name
                environment_info['location'] = (ENV_STORE_PATH + "/environments/{env_name}-{env_id}").format(env_name=environment_name,
                                                                                                             env_id=env_id)
                request_handler_thread = environment_handler.EnvironmentHandler(env_id, environment_def, environment_info, action='create')
                thread.start_new_thread(start_thread, (request_handler_thread, ))

                response.headers['location'] = ('/environments/{env_id}').format(env_id=env_id)
        except OSError as oe:
            fmlogging.error(oe)
            # Send back service unavailable status
            response.status_code = 503

        return response

    def get(self):
        fmlogging.debug("Received GET request for all environments")
        resp_data = {}

        resp_data['data'] = dbhandler.get_environments()

        response = jsonify(**resp_data)
        response.status_code = 200
        return response

class EnvironmentRestResource(Resource):
    def get(self, env_id):

        resp_data = {}

        resp_data['data'] = dbhandler.get_environment(env_id)

        response = jsonify(**resp_data)
        response.status_code = 200
        return response

    def delete(self, env_id):
        fmlogging.debug("Received DELETE request for environment %s" % env_id)
        resp_data = {}

        response = jsonify(**resp_data)
        environment_info = {}

        env_obj = db_handler.DBHandler().get_environment(env_id)
        if env_obj:
            app_list = db_handler.DBHandler().get_apps_on_environment(env_id)
            if app_list and len(app_list) > 0:
                response.status_code = 412
                response.status_message = 'Environment cannot be deleted as there are applications still running on it.'
                return response            
            environment_name = env_obj[db_handler.ENV_NAME]
            environment_def = env_obj[db_handler.ENV_DEFINITION]
            environment_info['name'] = environment_name
            environment_info['location'] = (ENV_STORE_PATH + "/environments/{env_name}-{env_id}").format(env_name=environment_name,
                                                                                                         env_id=env_id)
            request_handler_thread = environment_handler.EnvironmentHandler(env_id, environment_def, environment_info, action='delete')
            thread.start_new_thread(start_thread, (request_handler_thread, ))

            response.headers['location'] = ('/environments/{env_id}').format(env_id=env_id)
            response.status_code = 201
        else:
            response.status_code = 404
        return response


class StacksResource(Resource):
    def post(self):
        fmlogging.debug("Received POST request to create resource stack")
        args = request.get_json(force=True)
        
        response = jsonify()
        response.status_code = 201

        args_dict = dict(args)
        
        try:
            # Handle resource creation request
            if not 'resource_info' in args_dict:
                response.status_code = 400
            else:
                deploy_id = dbhandler.add_resource_stack(args_dict['resource_info'])
                
                response.headers['location'] = ('/resource_stack/{deploy_id}').format(deploy_id=deploy_id)
        except OSError as oe:
            fmlogging.error(oe)
            # Send back service unavailable status
            response.status_code = 503

        return response

    def get(self):
        fmlogging.debug("Received GET request for all stacks.")
        resp_data = {}

        resp_data['data'] = dbhandler.get_resource_stacks()

        response = jsonify(**resp_data)
        response.status_code = 200
        return response

class StackResource(Resource):
    def get(self, stack_id):

        resp_data = {}

        resp_data['data'] = dbhandler.get_resource_stack(stack_id)

        response = jsonify(**resp_data)
        response.status_code = 200
        return response

    def delete(self, stack_id):
        fmlogging.debug("Received DELETE request for stack %s" % stack_id)
        resp_data = {}

        resp_data['data'] = dbhandler.delete_resource_stack(stack_id)

        response = jsonify(**resp_data)
        response.status_code = 201
        return response

api.add_resource(AppsRestResource, '/apps')
api.add_resource(AppRestResource, '/apps/<app_id>')

api.add_resource(EnvironmentsRestResource, '/environments')
api.add_resource(EnvironmentRestResource, '/environments/<env_id>')

api.add_resource(StacksResource, '/resource_stacks')
api.add_resource(StackResource, '/resource_stacks/<stack_id>')
api.add_resource(ResourcesResource, '/resources')
api.add_resource(ResourceResource, '/resources/<resource_id>')

if __name__ == '__main__':
    if not os.path.exists(APP_STORE_PATH):
        os.makedirs(APP_STORE_PATH)
    fmlogging = fm_logger.Logging()
    fmlogging.info("Starting LME server")

    from gevent.wsgi import WSGIServer
    http_server = WSGIServer(('', 5002), app)
    http_server.serve_forever()

    #app.run(debug=True, threaded=True, host='0.0.0.0', port=5002)
