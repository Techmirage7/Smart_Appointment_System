# Booking System Web Application

A full-featured booking and payment management system built with **Flask** and **MySQL**. This project supports user registration, service provider management, bookings, payments, notifications, reviews, and admin controls.

## Features

- User registration and login (Customer, Service Provider, Admin)
- Service listing and management
- Booking creation, cancellation, and status tracking
- Payment processing and invoice generation
- Notifications for users and providers
- Reviews and ratings for service providers
- Admin dashboard for managing users, services, and providers
- Provider earnings dashboard

## Tech Stack

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript (Jinja2 templates)
- **Database:** MySQL

## Project Structure

```
bp/
  app.py                # Main Flask application
  static/               # Static files (CSS, JS, images)
    css/style.css
    js/main.js
    images/
  templates/            # HTML templates (Jinja2)
    base.html
    index.html
    login.html
    register.html
    user_dashboard.html
    provider_dashboard.html
    admin_dashboard.html
    payments.html
    payment.html
    invoice.html
    invoice_template.html
```

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd <repo-directory>
```

### 2. Install Dependencies

Create a virtual environment (recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install required packages:

```bash
pip install flask mysql-connector-python
```

### 3. Configure the Database

- Ensure you have MySQL installed and running.
- Create a database named `BookingSystem`.
- Update the `db_config` in `app.py` if your MySQL credentials differ:

```python
# In app.py
# db_config = {
#     'host': 'localhost',
#     'user': 'root',
#     'password': 'your-password',
#     'database': 'BookingSystem'
# }
```
- The app will attempt to set up and update the schema on first run. Make sure your MySQL user has privileges to create/alter tables.

### 4. Run the Application

```bash
python app.py
```

- The app will be available at [http://127.0.0.1:5000/](http://127.0.0.1:5000/)(coming soon)

### 5. Accessing the App

- Register as a new user (Customer or Service Provider)
- Admin users can be created directly in the database (see `Admin` table)
- Explore dashboards, make bookings, process payments, and more

## API Endpoints

The app provides several RESTful API endpoints for AJAX and frontend integration. Some key endpoints:

- `/api/services` - List/add services
- `/api/user/bookings` - Get user bookings
- `/api/user/payments` - Get user payments
- `/api/user/notifications` - Get notifications
- `/api/provider/earnings` - Provider earnings summary
- `/api/admin/providers` - Admin: list service providers
- `/api/admin/providers/<id>/approve` - Admin: approve provider

See `app.py` for the full list and details.

## Customization

- Update static files in `static/` for custom styles and scripts.
- Modify templates in `templates/` for UI changes.
- Extend `app.py` to add new features or endpoints.

## Contribution

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a new branch (`git checkout -b feature/your-feature`)
3. Commit your changes
4. Push to your fork and submit a pull request

## License

This project is open-source and available under the [MIT License](LICENSE).

## Acknowledgements

- Flask documentation: https://flask.palletsprojects.com/
- MySQL documentation: https://dev.mysql.com/doc/ 
