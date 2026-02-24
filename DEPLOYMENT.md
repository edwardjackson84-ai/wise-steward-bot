# Wise Steward: Cloud Deployment Guide

To receive webhooks from TradingView, your Python script (`tradelocker_executor.py`) must be running on a server that is publicly accessible on the internet. TradingView cannot send alerts to your personal laptop while it is asleep!

The easiest, cheapest, and most reliable way to host this Python Flask app is using a platform-as-a-service (PaaS) like **Render** or **Heroku**. 

Here is the step-by-step guide to deploying this script on **Render** (which has a great free tier).

## Step 1: Prepare the Files
To host your Python script, the server needs to know what dependencies to install. You need to create a `requirements.txt` file in the same folder as your script.

Create a file named `requirements.txt` with these two lines:
```text
Flask==3.0.0
requests==2.31.0
gunicorn==21.2.0
```
*(Gunicorn is a production-grade web server that Render uses to run Flask apps).*

## Step 2: Push to GitHub
Render connects directly to your GitHub account to deploy your code.
1. Create a free GitHub account if you don't have one.
2. Create a new **Private** repository (call it `wise-steward-bot`).
3. Upload `tradelocker_executor.py` and `requirements.txt` into that repository.

## Step 3: Set up Render
1. Go to [Render.com](https://render.com/) and sign up.
2. Click **New +** and select **Web Service**.
3. Connect your GitHub account and select your `wise-steward-bot` repository.
4. Fill out the deployment settings:
    *   **Name:** `wise-steward-webhook`
    *   **Environment:** `Python 3`
    *   **Build Command:** `pip install -r requirements.txt`
    *   **Start Command:** `gunicorn tradelocker_executor:app`
    *   *Note: If you renamed your python file, change `tradelocker_executor` to match your filename.*

## Step 4: Configure Environment Variables (CRITICAL)
Your Tradelocker credentials are read from environment variables to keep them secure. **Never hardcode your password into the Python script on GitHub.**

Scroll down to the **Environment Variables** section in Render. Add the following keys and your specific values:
*   `TRADELOCKER_EMAIL`: Your Hankotrade/Tradelocker email
*   `TRADELOCKER_PASSWORD`: Your password
*   `TRADELOCKER_SERVER`: e.g., `Hankotrade-Live`
*   `TRADELOCKER_API_URL`: `https://api.tradelocker.com`

## Step 5: Deploy and Get Your Webhook URL
1. Click **Create Web Service** at the bottom.
2. Render will spin up a server, install Python, download Flask, and start your app. This takes about 2-3 minutes.
3. Once the deployment says **"Live"**, look near the top left for your public URL. It will look something like this:
   `https://wise-steward-webhook.onrender.com`

## Step 6: Connect TradingView
Now that your server is live and listening on the internet:
1. Go to your TradingView chart.
2. Click the **Alert** button on your King David Multi-TF or Oliver Velez indicator.
3. Go to the **Notifications** tab in the alert menu.
4. Check the box for **Webhook URL**.
5. Paste your Render URL with `/webhook` added to the end.
   *Example: `https://wise-steward-webhook.onrender.com/webhook`*

Now, every time your Pine Script fires, TradingView will instantly POST the JSON directly to your new server, where the Python script will evaluate it and execute on TradeLocker!
