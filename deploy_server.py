import os
import re
import requests
import yaml
import tarfile
import shutil
import subprocess
import zipfile
import random
import string
import mysql.connector
import pyinputplus as pyip
import json
import py7zr
from bs4 import BeautifulSoup
from getpass import getpass
from mysql.connector import Error
from tqdm import tqdm

# utility functions
def download_file(url, dest):
    response = requests.get(url, stream=True, allow_redirects=True)
    if response.status_code == 200:
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        progress_bar = tqdm(total=total_size, unit='B', unit_scale=True, desc=os.path.basename(dest))
        
        # Create the directory if it doesn't exist
        if os.path.dirname(dest) and not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
        
        with open(dest, 'wb') as file:
            for chunk in response.iter_content(chunk_size=block_size):
                file.write(chunk)
                progress_bar.update(len(chunk))
        progress_bar.close()
        return True
    else:
        print("Failed to download file")
        return False

def extract_archive(file, dest):
    if file.endswith('.tar.xz'):
        with tarfile.open(file, 'r:xz') as tar_ref:
            tar_ref.extractall(dest)
    elif file.endswith('.zip'):
        with zipfile.ZipFile(file, 'r') as zip_ref:
            zip_ref.extractall(dest)
    elif file.endswith('.7z'):
        with py7zr.SevenZipFile(file, mode='r') as zip7_ref:
            zip7_ref.extractall(path=dest)
    else:
        print("Unsupported archive format")
        
def onerror(func, path, exc_info):
    import stat
    # Is the error an access error?
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise

def generate_db_name(recipe):
    name = recipe.get('name').replace(' ', '')
    random_string = ''.join(random.choices(string.hexdigits.upper(), k=6))
    return f"{name}_{random_string}"

# fetch build numbers
def fetch_build_numbers():
    artifact_url = 'https://runtime.fivem.net/artifacts/fivem/build_server_windows/master/' if os.name == 'nt' else 'https://runtime.fivem.net/artifacts/fivem/build_proot_linux/master/'
    if os.name == 'nt':
        search_url = r'(\d+)-[\da-f]+/server\.7z'
    else:
        search_url = r'(\d+)-[\da-f]+/fx\.tar\.xz'

    response = requests.get(artifact_url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    builds = {}
    recommended_build = None

    for link in soup.find_all('a', href=True):
        href = link['href']
        match = re.search(search_url, href)
        if match:
            build_number = match.group(1)
            builds[build_number] = artifact_url + href
            if 'LATEST RECOMMENDED' in link.text:
                recommended_build = build_number

    return builds, recommended_build

def fetch_recipes():
    recipes_url = 'https://raw.githubusercontent.com/solareon/fxserver-recipes/main/index.json'
    response = requests.get(recipes_url)
    response.raise_for_status()
    return response.json()

def validate_sql_connection(sql_info):
    try:
        connection = mysql.connector.connect(
            host=sql_info['ip'],
            port=sql_info['port'],
            user=sql_info['user'],
            password=sql_info['password'],
            collation='utf8mb4_unicode_ci',
        )

        if connection.is_connected():
            print("Successfully connected to the database")

            cursor = connection.cursor()
            cursor.execute("SELECT VERSION()")

            db_version = cursor.fetchone()
            print("Database version:", db_version[0])
            
            cursor.execute(f"SHOW DATABASES LIKE '{sql_info['db']}'")
            db_exists = cursor.fetchone()
            if not db_exists and sql_info['user'] == 'root':
                print(f"Database {sql_info['db']} does not exist. Creating it.")
                cursor.execute(f"CREATE DATABASE {sql_info['db']}")
                user_password = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
                cursor.execute(f"CREATE USER '{sql_info['db']}'@'localhost' IDENTIFIED BY '{user_password}'")
                cursor.execute(f"GRANT ALL PRIVILEGES ON {sql_info['db']}.* TO '{sql_info['db']}'@'localhost'")
                cursor.execute("FLUSH PRIVILEGES")
                db_connection_string = f"mysql://{sql_info['db']}:{user_password}@{sql_info['ip']}:{sql_info['port']}/{sql_info['db']}"
                print(f"Database {sql_info['db']} created successfully.")
                return True, db_connection_string
            elif not db_exists:
                print(f"Database {sql_info['db']} does not exist. Exiting.")
                return False
                
            cursor.close()
            connection.close()
            db_connection_string = f"mysql://{sql_info['db']}:{sql_info['db']}@{sql_info['ip']}:{sql_info['port']}/{sql_info['db']}"
            return True, db_connection_string

    except Error as e:
        print("Error while connecting to MySQL", e)
        return False

def connect_database(sql_info):
    try:
        connection = mysql.connector.connect(
            host=sql_info['ip'],
            port=sql_info['port'],
            user=sql_info['user'],
            password=sql_info['password'],
            database=sql_info['db'],
            collation='utf8mb4_unicode_ci',
            connect_timeout=3600
        )
        if connection.is_connected():
            print("Successfully connected to the database")
            return connection
    except Error as e:
        print("Error while connecting to database", e)
        return None

def prompt_user(builds, recommended_build):
    print(f"Recommended build number: \033[92m{recommended_build}\033[0m")
    build_number = pyip.inputStr("Enter the server artifact build number (blank for recommended): ", default=recommended_build,
        applyFunc=lambda x: x.strip() if x else recommended_build)

    if build_number not in builds:
        print("Invalid build number. Exiting.")
        return None

    artifact_url = builds[build_number]

    custom_url = pyip.inputStr("Enter a custom recipe URL (leave blank to select from available recipes): ", blank=True).strip()
    if custom_url:
        if not custom_url.endswith('.yaml'):
            print("Invalid URL. URL must end with '.yaml'. Exiting.")
            return None
        recipe_url = custom_url
    else:
        recipes = fetch_recipes()
        recipe_names = [recipe['name'] for recipe in recipes]
        recipe_menu = pyip.inputMenu(recipe_names, numbered=True, prompt="Select a recipe: \n")
        selected_recipe = next((recipe for recipe in recipes if recipe['name'] == recipe_menu), None)
        if not selected_recipe:
            print("Invalid recipe selection. Exiting.")
            return None
        recipe_url = selected_recipe['url']
    
    download_file(recipe_url, 'recipe.yaml')
    with open('recipe.yaml', 'r') as file:
        recipe = yaml.safe_load(file)
        
    remove_git = pyip.inputStr("Remove .git folder from the resources? (y/n): ", blank=True).strip()
    if remove_git.lower() == 'y':
        recipe['tasks'].append({
            'action': 'remove_git',
            'path': '.git'
        })
        with open('recipe.yaml', 'w') as save_recipe:
            save_recipe.write(yaml.dump(recipe))

    sql_ip = pyip.inputStr("Enter SQL server IP address (blank for localhost): ", default='localhost', blank=True,
                           applyFunc=lambda x: x.strip() if x else 'localhost')
    sql_port = pyip.inputInt("Enter SQL server port (default 3306): ", default=3306, blank=True,
                             applyFunc=lambda x: x if x else 3306)
    sql_user = pyip.inputStr("Enter SQL server username (blank for root): ", default='root', blank=True,
                             applyFunc=lambda x: x.strip() if x else 'root')
    sql_password = pyip.inputPassword("Enter SQL server password: ", blank=True)
    sql_db = pyip.inputStr("Enter SQL database name (leave blank to generate one, must be root): ", blank=True)
    if not sql_db:
        sql_db = generate_db_name(recipe)
            
    db_connection, db_connection_string = validate_sql_connection({
        'ip': sql_ip,
        'port': sql_port,
        'user': sql_user,
        'password': sql_password,
        'db': sql_db
    })
    if not db_connection:
        print("Exiting.")
        return None
    
    deploy_folder = input(f"Enter the folder to store recipe contents (leave blank for '{sql_db}'): ").strip() or sql_db
    print(f"Deploying to folder: {deploy_folder}")
    
    deploy_path = os.path.join('fxServer', 'txData', deploy_folder)
    
    if os.path.exists(deploy_path):
        remove_folder = input(f"Folder {deploy_folder} already exists. Remove it? (y/n): ").strip()
        if remove_folder.lower() == 'y':
            shutil.rmtree(deploy_path, onerror=onerror)
        else:
            print("Exiting.")
            return None
        
    sv_license = pyip.inputStr("Enter the server license key: ", allowRegexes=[r'^cfxk_[A-Za-z0-9]{20}_[A-Za-z0-9]{6}$'])
    server_name = pyip.inputStr("Enter the server name: ", blank=True).strip() or recipe.get('name')
    max_clients = pyip.inputStr("Enter the maximum number of clients: ", blank=True).strip() or '48'
    recipe_name = recipe.get('name')
    recipe_author = recipe.get('author')
    recipe_description = recipe.get('description')

    return {
        "artifact_url": artifact_url,
        "recipe_url": recipe_url,
        "sql_ip": sql_ip,
        "sql_port": sql_port,
        "sql_user": sql_user,
        "sql_password": sql_password,
        "sql_db": sql_db,
        "deploy_folder": deploy_folder,
        "db_connection_string": db_connection_string,
        "sv_license": sv_license,
        "server_name": server_name,
        "max_clients": max_clients,
        "recipe_name": recipe_name,
        "recipe_author": recipe_author,
        "recipe_description": recipe_description
    }, recipe

def replace_monitor_folder(dest):
    txadmin_latest_url = "https://github.com/tabarra/txAdmin/releases/latest/download/monitor.zip"
    download_file(txadmin_latest_url, 'txAdmin.zip')
    extract_archive('txAdmin.zip', 'txAdmin')
    monitor_src = 'txAdmin'
    if os.name == 'nt':
        monitor_dest = os.path.join(dest, 'citizen', 'system_resources', 'monitor')
    else:
        monitor_dest = os.path.join(dest, 'alpine', 'opt', 'cfx-server', 'citizen', 'system_resources', 'monitor')

    if os.path.exists(monitor_dest):
        shutil.rmtree(monitor_dest, onerror=onerror)

    shutil.copytree(monitor_src, monitor_dest)
    shutil.rmtree('txAdmin', onerror=onerror)
    os.remove('txAdmin.zip')

def process_recipe(recipe, deploy_folder, sql_info):
    recipe_dest = os.path.join('fxServer', 'txData', deploy_folder)
    os.makedirs(recipe_dest, exist_ok=True)
    
    for task in recipe['tasks']:
        action = task['action']
        keys = ', '.join([f"\033[94m{key}:\033[0m {task.get(key, None)}" for key in task.keys() if key != 'action'])
        print(f"\033[92mProcessing task\033[0m: {action} ({keys})")
        if action == 'download_github':
            src = task['src']
            ref = task.get('ref', None)
            dest = os.path.join(recipe_dest, task['dest'])
            result = subprocess.run(['git', 'clone', '--quiet', '--branch', ref, src, dest]) if ref else subprocess.run(['git', 'clone', '--quiet', src, dest])
            if result.returncode != 0:
                print(f"Failed to execute task: {task}")
                continue

            subpath = task.get('subpath')
            if subpath:
                subpath_dest = os.path.join(dest, subpath)
                if os.path.exists(subpath_dest):
                    for root, dirs, files in os.walk(subpath_dest):
                        for file in files:
                            shutil.move(os.path.join(root, file), os.path.join(dest, file))
                        for dir in dirs:
                            shutil.move(os.path.join(root, dir), os.path.join(dest, dir))
                    shutil.rmtree(subpath_dest, onerror=onerror)
        elif action == 'move_path':
            shutil.move(os.path.join(recipe_dest, task['src']), os.path.join(recipe_dest, task['dest']))
        elif action == 'copy_path':
            src = os.path.join(recipe_dest, task['src'])
            dest = os.path.join(recipe_dest, task['dest'])
            if not os.path.exists(os.path.dirname(dest)):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
            overwrite = task.get('overwrite', False)
            if overwrite and os.path.exists(dest):
                if os.path.isfile(dest):
                    os.remove(dest)
                elif os.path.isdir(dest):
                    shutil.rmtree(dest, onerror=onerror)
            if not overwrite and os.path.exists(dest):
                print(f"Skipping task: Destination path already exists: {dest}")
                continue
            if os.path.isfile(src):
                shutil.copy(src, dest)
            elif os.path.isdir(src):
                shutil.copytree(src, dest)
        elif action == 'download_file':
            download_file(task['url'], os.path.join(recipe_dest, task['path']))
        elif action == 'unzip':
            extract_archive(os.path.join(recipe_dest, task['src']), os.path.join(recipe_dest, task['dest']))
        elif action == 'remove_path':
            shutil.rmtree(os.path.join(recipe_dest, task['path']), onerror=onerror)
        elif action == 'connect_database':
            db_connection = connect_database(sql_info)
            if not db_connection:
                print("Failed to connect to database. Exiting.")
                return
        elif action == 'query_database':
            file = task.get('file')
            query = task.get('query')
            if not file and not query:
                print("Skipping task: No file or query provided.")
                continue
            if file:
                with open(os.path.join(recipe_dest, file), 'r') as query_file:
                    query = query_file.read()
            db_connection = connect_database(sql_info)
            db_connection.cursor().execute(query, multi=True)
        elif action == 'ensure_dir':
            os.makedirs(os.path.join(recipe_dest, task['path']), exist_ok=True)
        elif action == 'write_file':
            file_path = os.path.join(recipe_dest, task['file'])
            append = task.get('append', False)
            with open(file_path, 'a' if append else 'w') as f:
                f.write(task['data'])
        elif action == 'remove_git':
            for root, dirs, files in os.walk(recipe_dest):
                for dir in dirs:
                    if dir == '.git':
                        shutil.rmtree(os.path.join(root, dir), onerror=onerror)
        else:
            print(f"Skipping unsupported action: {task['action']}")

def update_server_cfg(deploy_folder, server_config):
    server_cfg_path = os.path.join('fxServer', 'txData', deploy_folder, 'server.cfg')
    with open(server_cfg_path, 'r') as file:
        server_cfg = file.read()
    
    # Replace serverEndpoints with connection endpoints
    server_endpoints = [
        'endpoint_add_tcp "0.0.0.0:30120"',
        'endpoint_add_udp "0.0.0.0:30120"',
    ]
    server_cfg = server_cfg.replace('{{serverEndpoints}}', '\n'.join(server_endpoints))
    server_cfg = server_cfg.replace('{{maxClients}}', server_config['max_clients'])
    server_cfg = server_cfg.replace('{{svLicense}}', server_config['svLicense'])
    server_cfg = server_cfg.replace('{{serverName}}', server_config['serverName'])
    server_cfg = server_cfg.replace('{{recipeName}}', server_config['recipeName'] or 'Unknown Recipe')
    server_cfg = server_cfg.replace('{{recipeAuthor}}', server_config['recipeAuthor'] or 'Unknown Author')
    server_cfg = server_cfg.replace('{{recipeDescription}}', server_config['recipeDescription'] or 'No description provided.')
    server_cfg = server_cfg.replace('{{dbConnectionString}}', server_config['dbConnectionString'])
    server_cfg = server_cfg.replace('{{addPrincipalsMaster}}', '# Deployer Note: this admin master has no identifiers to be automatically added.\n# add_principal identifier.discord:111111111111111111 group.admin #example')
    
    # Replace the server.cfg file
    with open(server_cfg_path, 'w') as file:
        file.write(server_cfg)

def create_txadmin_config(server_config, deploy_folder):
    json_path = os.path.join('fxServer', 'txData', 'default')
    current_dir = os.getcwd()
    deploy_path = os.path.join(current_dir, 'fxServer', 'txData', deploy_folder)
    os.makedirs(json_path, exist_ok=True)
    
    with open('example_config.json', 'r', encoding="utf-8") as file:
        config = json.load(file)
        config['global']['serverName'] = server_config['serverName']
        config['fxRunner']['serverDataPath'] = deploy_path
        config['fxRunner']['cfgPath'] = f"{deploy_path}/server.cfg"
    
    with open(os.path.join(json_path, 'config.json'), 'w') as file:
        json.dump(config, file, indent=2)

def process_template_deploy(builds):
    print("Found deploy.json file. Using the values from the file.")
    with open('deploy.json', 'r', encoding="utf-8") as file:
        deploy_recipe = json.load(file)
    db_connection, db_connection_string = validate_sql_connection({
        'ip': deploy_recipe['sqlServer'],
        'port': deploy_recipe['sqlPort'],
        'user': deploy_recipe['sqlUser'],
        'password': deploy_recipe['sqlPass'],
        'db': deploy_recipe['sqlDb']
    })
    if not db_connection:
        print("Exiting.")
        return None
    
    recipe_location = 'recipe.yaml' if deploy_recipe['recipeUrl'].startswith('http') else deploy_recipe['recipeUrl']
    if recipe_location == 'recipe.yaml':
        download_file(deploy_recipe['recipeUrl'], recipe_location)
    elif not os.path.exists(recipe_location):
        print("Recipe file not found. Exiting.")
        return None
        
    with open(recipe_location, 'r') as file:
        recipe = yaml.safe_load(file)
        
    if deploy_recipe['removeGit']:
        recipe['tasks'].append({
            'action': 'remove_git',
            'path': '.git'
        })
    
    return {
        "artifact_url": builds[deploy_recipe['artifact']],
        "recipe_url": deploy_recipe['recipeUrl'],
        "sql_ip": deploy_recipe['sqlServer'],
        "sql_port": deploy_recipe['sqlPort'],
        "sql_user": deploy_recipe['sqlUser'],
        "sql_password": deploy_recipe['sqlPass'],
        "sql_db": deploy_recipe['sqlDb'],
        "deploy_folder": deploy_recipe['deployFolder'],
        "db_connection_string": db_connection_string,
        "sv_license": deploy_recipe['svLicenseKey'],
        "server_name": deploy_recipe['serverName'],
        "max_clients": deploy_recipe['maxClients'],
        "recipe_name": recipe.get('name'),
        "recipe_author": recipe.get('author'),
        "recipe_description": recipe.get('description')
    }, recipe

def main():
    print("Welcome to the fxServer server deployment script with txAdmin recipe support.")
    #check if git is available
    if not shutil.which('git'):
        print("Git is required to download recipes. Please install git and try again.")
        return
    builds, recommended_build = fetch_build_numbers()
    if os.path.exists('deploy.json'):
        user_inputs, recipe = process_template_deploy(builds)
    else:
        user_inputs, recipe = prompt_user(builds, recommended_build)

    if not user_inputs:
        return

    artifact_url = user_inputs['artifact_url']
    recipe_url = user_inputs['recipe_url']
    deploy_folder = user_inputs['deploy_folder']
    sql_info = {
        'ip': user_inputs['sql_ip'],
        'port': user_inputs['sql_port'],
        'user': user_inputs['sql_user'],
        'password': user_inputs['sql_password'],
        'db': user_inputs['sql_db']
    }
    
    server_config = {
        'svLicense': user_inputs['sv_license'],
        'max_clients': user_inputs['max_clients'],
        'serverName': user_inputs['server_name'],
        'recipeName': user_inputs['recipe_name'],
        'recipeAuthor': user_inputs['recipe_author'],
        'recipeDescription': user_inputs['recipe_description'],
        'dbConnectionString': user_inputs['db_connection_string']
    }
        
    # Print Server setup data for confirmation
    print("\nServer setup data:")
    print(f"Artifact URL: {artifact_url}")
    print(f"Recipe URL: {recipe_url}")
    print(f"Recipe Name: {server_config['recipeName']}")
    print(f"Recipe Author: {server_config['recipeAuthor']}")
    print(f"Recipe Description: {server_config['recipeDescription']}")
    print(f"Deploy folder: {deploy_folder}")
    print(f"SQL IP: {sql_info['ip']}")
    print(f"SQL Port: {sql_info['port']}")
    print(f"SQL User: {sql_info['user']}")
    print(f"SQL Database: {sql_info['db']}")
    print(f"Server License: {server_config['svLicense']}")
    print(f"Server Name: {server_config['serverName']}")
    print(f"Max Clients: {server_config['max_clients']}")
    
    # Get user confirmation to deploy
    confirm_deploy = pyip.inputYesNo("Deploy the server with the above configuration? (y/n): ")
    if not confirm_deploy:
        print("Exiting.")
        return

    print("Starting server install...")
    fx_server_archive = 'server.7z' if os.name == 'nt' else 'fx.tar.xz'
    download_file(artifact_url, fx_server_archive)
    extract_archive(fx_server_archive, 'fxServer')
    print("Updating txAdmin...")
    replace_monitor_folder('fxServer')
    process_recipe(recipe, deploy_folder, sql_info)
    
    # Setup server configuration
    print("Setting up server configuration...")
    update_server_cfg(deploy_folder, server_config)
    
    # Create config.json file for txAdmin
    print("Creating txAdmin config.json file...")
    create_txadmin_config(server_config, deploy_folder)
    
    print("Cleaning up...")
    if os.path.exists(fx_server_archive):
        os.remove(fx_server_archive)
    if os.path.exists('recipe.yaml') and recipe_url.startswith('http'):
        os.remove('recipe.yaml')

    print("Server setup complete.")

if __name__ == "__main__":
    main()
