# Financial Tracker User Manual

## Table of Contents
1. Introduction
2. Accessing the Application
3. Logging In
4. Adding a Purchase Order (PO)
5. Editing a Purchase Order
6. Forecast Table & Export
7. File Uploads
8. Logging Out
9. Troubleshooting & Support

---

## 1. Introduction
Financial Tracker is a web application for managing purchase orders, forecasting inflows, and exporting financial data. It is designed for ease of use and secure access.

## 2. Accessing the Application
- Open your web browser and go to: [http://localhost:5000](http://localhost:5000) (or your server's address).
- The application may be deployed using Docker. See the Docker documentation for setup instructions.

## 3. Logging In
- You must log in to access most features.
- Go to the login page and enter your credentials.
- Only the login, static files, and Google authorization routes are accessible without logging in.

## 4. Adding a Purchase Order (PO)
- Navigate to the "Add PO" or "Add Unconfirmed Order" page.
- Fill in the required details. All orders added here are marked as "Unconfirmed" by default.
- Submit the form to add the PO.

## 5. Editing a Purchase Order
- Go to the "Edit PO" page from the PO list or search.
- You can change all details.
- Save your changes.

## 6. Forecast Table & Export
- The "Forecast" page displays a table of forecasted inflows, sourced from the latest processed data.
- All currency values are shown as whole numbers (no decimals), calculations are being done using decimals though.
- You can export the forecast as an Excel file. The Excel export also displays only whole numbers, including in the pivot table.

## 7. File Uploads
- Upload PO-related files (such as PDFs) via the provided upload forms.
- Uploaded files are processed and stored securely.

## 8. Logging Out
- Click the "Logout" button in the navigation bar to end your session.
- You will be redirected to the login page.

## 9. Troubleshooting & Support
- If you encounter issues:
  - Ensure you are logged in.
  - Refresh the page or clear your browser cache.
  - If running locally, make sure Docker containers are running (`docker compose up -d --build`).
  - Check the logs in the `logs/` directory or via Docker Compose logs.
- For further support, contact your system administrator or refer to the project README and Docker documentation.

---

For technical setup, see `README.md` and `docker_README.md`.
