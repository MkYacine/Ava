# Excalibur

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