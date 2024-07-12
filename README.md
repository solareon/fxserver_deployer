# fxServer deployer
Prompts user for configuration information to deploy a fxServer installation with latest txAdmin by following a txAdmin compatible recipe. Also capable of following a local recipe with the presence of a deploy.json. Built for Linux server deployment but should support Windows server deployments as well

# Support
- [Discord](https://discord.gg/TZFBBHvG6E)

# Credits
- [tabarra](https://github.com/tabarra) for txAdmin
- [citizenfx](https://github.com/citizenfx) for fivem

## Requirements
- A working SQL server.
- Python 3 with `pip`
- `git` cli tools installed

## Notes
- If a root user is specified during deployment and database does not exist or is blank, a new database and user will be created and stored in the server.cfg file.

## How to use
To use this repository, follow these steps:

1. Clone the repository to your local machine:
    ```
    git clone https://github.com/solareon/fxserver_deployer
    ```

2. Navigate to the cloned repository:
    ```
    cd fxserver_deployer
    ```

3. Install the required Python packages using pip:
    ```
    pip install -r requirements.txt
    ```

4. Execute the `deploy_server.py` script to deploy the fxServer installation:
    ```
    python3 deploy_server.py
    ```

That's it! You have successfully deployed the fxServer.

## Running the server

To run the server, use the following commands based on your operating system:

- For Windows, run the `run.bat` file:
    ```
    run.bat
    ```

- For Linux, run the `run.sh` file:
    ```
    ./run.sh
    ```

Make sure you have the necessary permissions to execute the script. Happy server running!


## Template deployment (advanced users)
If you are looking to deploy the same server multiple times you can provide the input variables into a `deploy.json`, below is a description of the options required. If deploying to the same database it is recommended that you include a step to drop all tables in your database within a step.


| **Variable**     | **Type**    | **Description**                                                            |
|------------------|-------------|----------------------------------------------------------------------------|
| `artifact`       | String      | Artifact identifier for the deployment.                                    |
| `recipeUrl`      | String (URL)| URL to the recipe YAML file. (local files also supported)                                               |
| `sqlServer`      | String      | Hostname of the SQL server.                                                |
| `sqlUser`        | String      | Username for the SQL server.                                               |
| `sqlPass`        | String      | Password for the SQL server.                                               |
| `sqlDb`          | String      | Database name on the SQL server.                                           |
| `sqlPort`        | String      | Port number for the SQL server.                                            |
| `serverName`     | String      | Name of the server.                                                        |
| `deployFolder`   | String      | Name of the folder where the deployment will be stored.                    |
| `svLicenseKey`   | String      | License key for the server.                                                |
| `maxClients`     | String      | Maximum number of clients that can connect to the server.                  |
| `removeGit`      | Boolean     | Flag indicating whether to remove Git after deployment (`true` or `false`).|


## Contributing

Contributions are welcome! If you encounter any issues or have suggestions for improvements, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more information.

