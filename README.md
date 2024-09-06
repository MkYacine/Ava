# Excalibur

## To do
- Fix sound issue when calls are made from the VM
- Buy and set up a domain
- Once a domain is setup, setup SSL to secure the connection and enable HTTPS
- Clean up the virtual machine and remove any unused dependencies (use new requirements.txt)
- Write unit tests and setup CI/CD jobs

## Setting up the ngrok server

### First-time setup
1. Open the ngrok configuration:
   ```
   ngrok config edit
   ```
2. Insert the configuration text (make sure localhost is set to port 5000)
3. Start the tunnel:
   ```
   ngrok start my_tunnel_name
   ```

### Subsequent uses
Simply start the tunnel:
   ```
   ngrok start my_tunnel_name
   ```

## Starting the Flask server   
   ```
   python twilio_handlers.py
   ```

## Launching the Streamlit app
   ```
   streamlit run app.py
   ```

## Important note
If you decide to switch to your phone as the initial caller, don't forget to update the webhook link in the Twilio dashboard for that phone number to point to the ngrok link.


### Deploying the app google cloud service:
That's great that you have a paid ngrok account! This gives you more flexibility and stability. Given this information, we can modify the setup slightly. Here's a step-by-step guide to deploy your application on Google Compute Engine (GCE) using your paid ngrok account:

1. Set up a Google Compute Engine instance:
   - Go to Google Cloud Console and create a new VM instance
   - Choose a machine type (e.g., e2-medium)
   - Select Ubuntu as the operating system
   - Allow HTTP and HTTPS traffic in the firewall rules

2. Set up the environment:
   - SSH into your instance (you can do this directly from the GCP console)
   - Update the system: `sudo apt update && sudo apt upgrade -y`
   - Install Python and pip: `sudo apt install python3 python3-pip -y`
   - Install other necessary tools: `sudo apt install git nginx -y`

3. Clone and set up your application:
   ```
   git clone <your-repository-url>
   cd <your-project-directory>
   pip3 install -r requirements.txt
   ```

4. Set up ngrok:
   - Download and install ngrok: 
     ```
     curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list && sudo apt update && sudo apt install ngrok
     ```
   - Authenticate ngrok: `ngrok config add-authtoken <your-authtoken>`
   - Create your ngrok config file (ngrok.yml) with your custom domain

5. Set up environment variables:
   - Create a .env file in your project directory with all necessary variables

6. Create systemd services:
   For Flask app (save as `/etc/systemd/system/flask_app.service`):
   ```
   [Unit]
   Description=Flask App
   After=network.target

   [Service]
   User=<your-username>
   WorkingDirectory=/path/to/your/project
   ExecStart=/usr/bin/python3 /path/to/your/flask_app.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   For Streamlit app (save as `/etc/systemd/system/streamlit_app.service`):
   ```
   [Unit]
   Description=Streamlit App
   After=network.target

   [Service]
   User=<your-username>
   WorkingDirectory=/path/to/your/project
   ExecStart=/usr/local/bin/streamlit run /path/to/your/streamlit_app.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   For ngrok (save as `/etc/systemd/system/ngrok.service`):
   ```
   [Unit]
   Description=ngrok
   After=network.target

   [Service]
   User=<your-username>
   WorkingDirectory=/path/to/your/project
   ExecStart=/usr/local/bin/ngrok start --all --config /path/to/your/ngrok.yml
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

7. Start and enable the services:
   ```
   sudo systemctl start flask_app streamlit_app ngrok
   sudo systemctl enable flask_app streamlit_app ngrok
   ```

8. Set up Nginx as a reverse proxy:
   Create a new Nginx config file (e.g., `/etc/nginx/sites-available/myapp`):
   ```
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://localhost:8501;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
       }
   }
   ```
   Enable the site: `sudo ln -s /etc/nginx/sites-available/myapp /etc/nginx/sites-enabled`
   Test and reload Nginx: `sudo nginx -t && sudo systemctl reload nginx`

9. Set up SSL with Let's Encrypt:
   ```
   sudo apt install certbot python3-certbot-nginx -y
   sudo certbot --nginx -d your-domain.com
   ```

10. Update your Twilio webhook URLs to point to your ngrok URL

This setup allows you to run everything on one GCE instance, with ngrok providing a stable URL for your Flask app (which Twilio will use), and Nginx serving your Streamlit app directly. The paid ngrok account ensures you have a consistent URL for your Flask app.

Remember to replace placeholders like `<your-username>`, `<your-repository-url>`, `your-domain.com`, etc., with your actual values.





Step 1 in detail:

1. Go to Google Cloud Console:
   - Visit https://console.cloud.google.com/
   - Sign in with your Google account

2. Create a new project (if you haven't already):
   - Click on the project dropdown at the top of the page
   - Click "New Project"
   - Name your project and click "Create"

3. Enable Compute Engine API:
   - In the left sidebar, go to "APIs & Services" > "Dashboard"
   - Click "+ ENABLE APIS AND SERVICES"
   - Search for "Compute Engine API" and enable it

4. Create a VM instance:
   - In the left sidebar, go to "Compute Engine" > "VM instances"
   - Click "CREATE INSTANCE"

5. Configure your instance:
   - Name: Choose a name for your instance
   - Region and Zone: Choose a region close to your users for better performance
   - Machine configuration:
     - Series: E2 (cost-effective general purpose)
     - Machine type: e2-micro (2 vCPU, 1 GB memory) - This should be sufficient for your app, but you can upgrade if needed
   - Boot disk:
     - Operating system: Ubuntu
     - Version: Ubuntu 20.04 LTS
     - Boot disk type: Standard persistent disk
     - Size: 10 GB (increase if you need more storage)
   - Firewall:
     - Allow HTTP traffic
     - Allow HTTPS traffic

6. Advanced options:
   - Networking:
     - Network tags: Add 'http-server' and 'https-server'
   - Management:
     - Availability policies: 
       - Automatic restart: On
       - On host maintenance: Migrate VM instance
     - Custom metadata:
       - Add an item with key 'startup-script' and value:
         ```
         #!/bin/bash
         apt update
         apt upgrade -y
         apt install -y python3 python3-pip git nginx
         ```
         This will automatically install necessary software when the instance starts

7. Click "Create" to create your instance

8. Set up a static IP (optional, but recommended):
   - In the left sidebar, go to "VPC network" > "External IP addresses"
   - Find your VM instance and change the type from "Ephemeral" to "Static"
   - Give it a name and save

9. Set up firewall rules:
   - In the left sidebar, go to "VPC network" > "Firewall"
   - Click "CREATE FIREWALL RULE"
   - Name: "allow-streamlit"
   - Direction of traffic: Ingress
   - Targets: Specified target tags
   - Target tags: http-server
   - Source filter: IP ranges
   - Source IP ranges: 0.0.0.0/0
   - Protocols and ports: Specified protocols and ports
   - Check "tcp" and enter "8501" (Streamlit's default port)
   - Click "Create"

10. Connect to your instance:
    - On the VM instances page, click the "SSH" button next to your instance name
    - This will open a browser window with an SSH connection to your instance

This setup provides a cost-effective solution:
- The e2-micro instance is part of the Google Cloud Free Tier, giving you 720 hours per month (enough for one instance to run continuously).
- Using Ubuntu as the OS helps keep costs down.
- The startup script automates some of the initial setup, saving you time.

Remember, while this setup is designed to be cost-effective, you may still incur some charges depending on your usage and other Google Cloud resources. Always monitor your billing and set up budget alerts in the Google Cloud Console to avoid unexpected costs.

After setting up the instance, you can proceed with the rest of the deployment steps I provided earlier, starting from cloning your repository and setting up your application.