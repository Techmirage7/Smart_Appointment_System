from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response
import mysql.connector
import re
import os
from datetime import datetime, timedelta
import hashlib
import json
import sys
import time

app = Flask(__name__)
app.secret_key = 'your-secret-key'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Custom JSON encoder to handle datetime objects
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, timedelta):
            hours, remainder = divmod(obj.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f'{hours:02d}:{minutes:02d}'
        return super().default(obj)

app.json_encoder = CustomJSONEncoder

# =====================================================
# DATABASE CONFIGURATION AND UTILITY FUNCTIONS
# =====================================================

# MySQL Configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'P##8954',
    'database': 'BookingSystem'
}

# Helper Functions
def get_db():
    """Get a new database connection"""
    return mysql.connector.connect(**db_config)

def hash_password(password):
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def setup_database():
    """Setup database and fix any issues"""
    try:
        # Connect to the database
        print("Setting up database...")
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Check for Timestamp column in Notifications
        cursor.execute("SHOW COLUMNS FROM Notifications LIKE 'Timestamp'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE Notifications ADD COLUMN Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            db.commit()
            print("Added Timestamp column to Notifications table")
        
        # Check for PaymentStatus column in Bookings
        cursor.execute("SHOW COLUMNS FROM Bookings LIKE 'PaymentStatus'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE Bookings ADD COLUMN PaymentStatus VARCHAR(20) DEFAULT 'Not Paid'")
            db.commit()
            print("Added PaymentStatus column to Bookings table")
        
        # PAYMENTS TABLE FIXES - Start with detailed checks
        print("Checking Payments table structure...")
        
        # First check if the table exists
        cursor.execute("SHOW TABLES LIKE 'Payments'")
        if not cursor.fetchone():
            print("Payments table doesn't exist! Creating it...")
            cursor.execute("""
                CREATE TABLE Payments (
                    P_ID INT AUTO_INCREMENT PRIMARY KEY,
                    B_ID INT,
                    CustomerID INT,
                    Amount DECIMAL(10,2),
                    PaymentDate DATE,
                    PaymentMethod ENUM('Credit Card', 'Debit Card', 'Net Banking', 'UPI'),
                    PaymentStatus VARCHAR(20) DEFAULT 'Success',
                    ProviderID INT,
                    FOREIGN KEY (B_ID) REFERENCES Bookings(B_ID)
                )
            """)
            db.commit()
            print("Created Payments table with ProviderID column")
        
        # Check for ProviderID column in Payments
        print("Checking for ProviderID column in Payments table...")
        cursor.execute("SHOW COLUMNS FROM Payments LIKE 'ProviderID'")
        if not cursor.fetchone():
            print("ProviderID column doesn't exist in Payments. Adding it...")
            cursor.execute("ALTER TABLE Payments ADD COLUMN ProviderID INT DEFAULT NULL")
            db.commit()
            print("Added ProviderID column to Payments table")
            
        # Count payments with null ProviderID
        cursor.execute("SELECT COUNT(*) as count FROM Payments WHERE ProviderID IS NULL")
        null_provider_count = cursor.fetchone()['count']
        print(f"Found {null_provider_count} payments with NULL ProviderID")
        
        if null_provider_count > 0:
            print("Updating payment records with provider IDs from their associated bookings...")
            # Update existing payments with provider IDs from their associated bookings
            cursor.execute("""
                UPDATE Payments p
                JOIN Bookings b ON p.B_ID = b.B_ID
                SET p.ProviderID = b.ProviderID
                WHERE p.ProviderID IS NULL AND b.ProviderID IS NOT NULL
            """)
            
            affected_rows = cursor.rowcount
            db.commit()
            print(f"Updated {affected_rows} payment records with provider IDs")
            
            # Check if there are still null ProviderIDs
            cursor.execute("SELECT COUNT(*) as count FROM Payments WHERE ProviderID IS NULL")
            still_null = cursor.fetchone()['count']
            
            if still_null > 0:
                print(f"Still have {still_null} payments with NULL ProviderID")
                
                # For any remaining null ProviderIDs, use CustomerID as a fallback
                cursor.execute("""
                    UPDATE Payments p
                    SET p.ProviderID = (
                        SELECT sp.U_ID 
                        FROM ServiceProvider sp 
                        LIMIT 1
                    )
                    WHERE p.ProviderID IS NULL
                """)
                
                affected_rows = cursor.rowcount
                db.commit()
                print(f"Updated remaining {affected_rows} payment records with a default provider ID")
        
        # Fix any null Provider IDs in Bookings
        cursor.execute("SELECT COUNT(*) as count FROM Bookings WHERE ProviderID IS NULL OR ProviderID = 0")
        null_bookings_count = cursor.fetchone()['count']
        print(f"Found {null_bookings_count} bookings with missing/zero provider ID")
        
        if null_bookings_count > 0:
            cursor.execute("SELECT U_ID FROM User WHERE UserType = 'ServiceProvider' LIMIT 1")
            provider = cursor.fetchone()
            
            if provider:
                cursor.execute("UPDATE Bookings SET ProviderID = %s WHERE ProviderID IS NULL OR ProviderID = 0", 
                             (provider['U_ID'],))
                
                affected_rows = cursor.rowcount
                db.commit()
                print(f"Fixed {affected_rows} bookings with missing provider ID")
        
        # Set default status for service providers
        cursor.execute("UPDATE ServiceProvider SET Status = 'Pending' WHERE Status IS NULL OR Status = ''")
        
        # Set default status for bookings
        cursor.execute("UPDATE Bookings SET Status = 'Pending' WHERE Status IS NULL OR Status = ''")
        
        # Set default payment status for bookings
        cursor.execute("UPDATE Bookings SET PaymentStatus = 'Not Paid' WHERE PaymentStatus IS NULL OR PaymentStatus = ''")
        
        # Set default status for payments
        cursor.execute("UPDATE Payments SET PaymentStatus = 'Success' WHERE PaymentStatus IS NULL OR PaymentStatus = ''")
        
        db.commit()
        cursor.close()
        db.close()
        print("Database setup completed successfully")
    except mysql.connector.Error as err:
        print(f"Database setup error: {err}")

# Run database setup on startup
setup_database()

# =====================================================
# ROUTES AND VIEWS
# =====================================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = hash_password(request.form['password'])
        user_type = request.form['user_type']
        
        print(f"Login attempt: Email={email}, Type={user_type}")
        
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        if user_type == 'admin':
            cursor.execute('SELECT * FROM Admin WHERE Email = %s', (email,))
            account = cursor.fetchone()
            if account and account['Password'] == password:
                print(f"Admin credentials valid for {email}. Setting session variables...")
                session['loggedin'] = True
                session['id'] = account['A_ID']
                session['email'] = account['Email']
                session['role'] = account.get('Role', 'Admin')  # Default to 'Admin' if Role is None
                session['name'] = account.get('Name', 'Admin')
                session['is_admin'] = True  # Additional flag to mark admin sessions
                
                # Print all session values for debugging
                print(f"Admin session variables set: id={session['id']}, role={session['role']}, name={session['name']}")
                return redirect(url_for('admin_dashboard'))
            else:
                print(f"Admin login failed for {email}: Invalid credentials")
        else:
            cursor.execute('SELECT * FROM User WHERE Email = %s', (email,))
            account = cursor.fetchone()
            
            if account:
                print(f"Found user: {account['Name']}, Type in DB: {account['UserType']}, Type from form: {user_type}")
            
            if account and account['UserType'] == user_type and account.get('Password') == password:
                print(f"Setting regular user session variables for {account['Name']}...")
                session['loggedin'] = True
                session['id'] = account['U_ID']
                session['email'] = account['Email']
                session['user_type'] = account['UserType']
                session['name'] = account['Name']
                session['phone'] = account['Phone_no']
                session['is_admin'] = False  # Explicitly mark as not admin
                
                print(f"User login successful: {account['Name']} ({account['UserType']})")
                
                # Direct redirection to appropriate dashboard based on user type
                if account['UserType'] == 'ServiceProvider':
                    print(f">>> Redirecting service provider {account['Name']} to provider dashboard")
                    return redirect(url_for('provider_dashboard'))
                else:
                    print(f">>> Redirecting customer {account['Name']} to user dashboard")
                    return redirect(url_for('user_dashboard'))
            else:
                if account:
                    print(f"Login failed: Password mismatch or user type mismatch")
                else:
                    print(f"Login failed: Account not found for {email}")
        
        flash('Invalid credentials!', 'error')
        cursor.close()
        db.close()
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = hash_password(request.form['password'])
        user_type = request.form['user_type']
        
        # Validate phone number
        if not re.match(r'^\d{10}$', phone):
            flash('Phone number must be exactly 10 digits!', 'error')
            return render_template('register.html')
        
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute('SELECT * FROM User WHERE Email = %s', (email,))
        account = cursor.fetchone()
        
        if account:
            flash('Email already exists!', 'error')
        else:
            # Add password to User table as well
            cursor.execute('INSERT INTO User (Name, Email, Phone_no, UserType, Password) VALUES (%s, %s, %s, %s, %s)',
                         (name, email, phone, user_type, password))
            db.commit()
            
            if user_type == 'ServiceProvider':
                cursor.execute('SELECT U_ID FROM User WHERE Email = %s', (email,))
                user_id = cursor.fetchone()['U_ID']
                cursor.execute('INSERT INTO ServiceProvider (U_ID, Specialization, Status) VALUES (%s, %s, %s)',
                             (user_id, request.form['specialization'], 'Pending'))
                db.commit()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    # Check for admin session in multiple ways
    is_admin = (
        'loggedin' in session and 
        (session.get('role') or session.get('is_admin', False) or session.get('id') in get_admin_ids())
    )
    
    if is_admin:
        print(f"Admin dashboard accessed by: {session.get('name')} (ID: {session.get('id')})")
        return render_template('admin_dashboard.html')
    else:
        print(f"Unauthorized admin dashboard access attempt. Session data: {session}")
    return redirect(url_for('login'))

@app.route('/user/dashboard')
def user_dashboard():
    if 'loggedin' in session and session.get('user_type'):
        print(f"User dashboard accessed by: {session.get('name')} with type: {session.get('user_type')}")
        if session.get('user_type') == 'ServiceProvider':
            print(f"Redirecting service provider to provider dashboard")
            return redirect(url_for('provider_dashboard'))
        return render_template('user_dashboard.html')
    return redirect(url_for('login'))

@app.route('/provider/dashboard')
def provider_dashboard():
    print(f"Provider dashboard accessed by: {session.get('name')} with type: {session.get('user_type')}")
    
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        print(f"Authentication valid for provider dashboard")
        # Get provider services
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get provider details
            cursor.execute('''
                SELECT u.*, sp.Specialization, sp.Status
                FROM User u
                JOIN ServiceProvider sp ON u.U_ID = sp.U_ID
                WHERE u.U_ID = %s
            ''', (session['id'],))
            
            provider = cursor.fetchone()
            print(f"Provider details: {provider}")
            
            # Get provider services
            cursor.execute('''
                SELECT s.*, 
                       (SELECT COUNT(*) FROM Bookings b WHERE b.S_ID = s.S_ID) as BookingCount
                FROM Services s
                WHERE s.ProviderID = %s
            ''', (session['id'],))
            
            services = cursor.fetchall()
            
            cursor.close()
            db.close()
            
            print(f"Rendering provider_dashboard.html with provider data and {len(services)} services")
            return render_template('provider_dashboard.html', 
                                  provider=provider, 
                                  services=services)
        except Exception as e:
            print(f"Error fetching provider data: {str(e)}")
            # Fallback to basic provider info if DB query fails
            return render_template('provider_dashboard.html', provider={
                'Name': session.get('name', ''),
                'Email': session.get('email', ''),
                'Phone': session.get('phone', '')
            }, services=[])
    print(f"Authentication failed for provider dashboard")
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('email', None)
    session.pop('role', None)
    session.pop('user_type', None)
    session.pop('name', None)
    session.pop('phone', None)
    return redirect(url_for('home'))

# API Routes
@app.route('/api/user/profile', methods=['GET'])
def get_user_profile():
    try:
        if 'loggedin' in session:
            return jsonify({
                'name': session.get('name', ''),
                'email': session.get('email', ''),
                'user_type': session.get('user_type', ''),
                'phone': session.get('phone', '')
            })
        # For unauthorized users, return empty profile instead of error
        # This helps avoid 401 errors in the frontend
        return jsonify({
            'name': '',
            'email': '',
            'user_type': '',
            'phone': ''
        })
    except Exception as e:
        print(f"Error in get_user_profile: {str(e)}")
        return jsonify({
            'name': '',
            'email': '',
            'user_type': '',
            'phone': ''
        })

@app.route('/api/admin/profile', methods=['GET'])
def get_admin_profile():
    # Check admin authentication in multiple ways
    is_admin = (
        'loggedin' in session and 
        (session.get('role') or session.get('is_admin', False) or session.get('id') in get_admin_ids())
    )
    
    if is_admin:
        return jsonify({
            'name': session.get('name', 'Admin'),
            'email': session.get('email', ''),
            'role': session.get('role', 'Admin'),
            'id': session.get('id', 0)
        })
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/services', methods=['GET'])
def get_services():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # For regular customers, only show services from approved providers
        if 'loggedin' in session and session.get('user_type') == 'Customer':
            cursor.execute('''
                SELECT s.*, u.Name as provider_name 
                FROM Services s
                JOIN User u ON s.ProviderID = u.U_ID
                JOIN ServiceProvider sp ON s.ProviderID = sp.U_ID
                WHERE sp.Status = 'Approved' AND (s.is_approved = 1 OR s.is_approved IS NULL)
            ''')
        # For admins, show all services
        elif 'loggedin' in session and session.get('role'):
            cursor.execute('''
                SELECT s.*, u.Name as provider_name, sp.Status as provider_status
                FROM Services s
                LEFT JOIN User u ON s.ProviderID = u.U_ID
                LEFT JOIN ServiceProvider sp ON s.ProviderID = sp.U_ID
            ''')
        # For service providers, show only their services
        elif 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
            cursor.execute('''
                SELECT s.*, u.Name as provider_name, 
                    (SELECT COUNT(*) FROM Bookings b WHERE b.S_ID = s.S_ID) as booking_count
                FROM Services s
                JOIN User u ON s.ProviderID = u.U_ID
                WHERE s.ProviderID = %s
            ''', (session['id'],))
        # For unauthenticated users or others, show only approved services from approved providers
        else:
            cursor.execute('''
                SELECT s.*, u.Name as provider_name
                FROM Services s
                JOIN User u ON s.ProviderID = u.U_ID
                JOIN ServiceProvider sp ON s.ProviderID = sp.U_ID
                WHERE sp.Status = 'Approved' AND (s.is_approved = 1 OR s.is_approved IS NULL)
            ''')
        
        services = cursor.fetchall()
        
        # Convert decimal values to float for JSON serialization
        for service in services:
            if 'Price' in service:
                service['Price'] = float(service['Price'])
        
        cursor.close()
        db.close()
        return jsonify(services)
    except Exception as e:
        print(f"Error fetching services: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/services', methods=['POST'])
def add_service():
    if 'loggedin' in session and session.get('role'):
        try:
            data = request.json
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # First check if the ProviderID column exists
            cursor.execute("SHOW COLUMNS FROM Services LIKE 'ProviderID'")
            has_provider_column = cursor.fetchone() is not None
            
            # First check if the is_approved column exists
            cursor.execute("SHOW COLUMNS FROM Services LIKE 'is_approved'")
            has_approval_column = cursor.fetchone() is not None
            
            # Get an approved service provider to assign the service to
            cursor.execute('''
                SELECT u.U_ID FROM User u
                JOIN ServiceProvider sp ON u.U_ID = sp.U_ID
                WHERE sp.Status = 'Approved'
                LIMIT 1
            ''')
            provider = cursor.fetchone()
            
            # If no approved provider exists, create the service without a provider
            if not provider:
                if has_provider_column and has_approval_column:
                    cursor.execute('''
                        INSERT INTO Services (Name, Price, Description, is_approved)
                        VALUES (%s, %s, %s, 1)
                    ''', (data['name'], data['price'], data['description']))
                else:
                    cursor.execute('''
                        INSERT INTO Services (Name, Price, Description)
                        VALUES (%s, %s, %s)
                    ''', (data['name'], data['price'], data['description']))
            else:
                # Assign the service to an approved provider
                if has_provider_column and has_approval_column:
                    cursor.execute('''
                        INSERT INTO Services (Name, Price, Description, ProviderID, is_approved)
                        VALUES (%s, %s, %s, %s, 1)
                    ''', (data['name'], data['price'], data['description'], provider['U_ID']))
                else:
                    cursor.execute('''
                        INSERT INTO Services (Name, Price, Description)
                        VALUES (%s, %s, %s)
                    ''', (data['name'], data['price'], data['description']))
            
            db.commit()
            cursor.close()
            db.close()
            return jsonify({'success': True, 'message': 'Service added successfully'})
        except Exception as e:
            print(f"Error adding service: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/user/bookings', methods=['GET'])
def get_user_bookings():
    try:
        if 'loggedin' in session:
            try:
                db = get_db()
                cursor = db.cursor(dictionary=True)
                
                if session.get('user_type') == 'Customer':
                    cursor.execute('''
                        SELECT b.*, s.Name as service_name,
                        (SELECT COUNT(*) FROM Payments p WHERE p.B_ID = b.B_ID) as payment_made,
                        (SELECT COUNT(*) FROM Cancellation c WHERE c.B_ID = b.B_ID) as is_cancelled
                        FROM Bookings b
                        JOIN Services s ON b.S_ID = s.S_ID
                        WHERE b.CustomerID = %s
                    ''', (session['id'],))
                else:  # Service Provider
                    cursor.execute('''
                        SELECT b.*, s.Name as service_name, u.Name as customer_name,
                        (SELECT COUNT(*) FROM Payments p WHERE p.B_ID = b.B_ID) as payment_made,
                        (SELECT COUNT(*) FROM Cancellation c WHERE c.B_ID = b.B_ID) as is_cancelled
                        FROM Bookings b
                        JOIN Services s ON b.S_ID = s.S_ID
                        JOIN User u ON b.CustomerID = u.U_ID
                        WHERE b.ProviderID = %s
                    ''', (session['id'],))
                    
                bookings = cursor.fetchall()
                
                # Set default values and handle datetime
                for booking in bookings:
                    booking['payment_made'] = int(booking.get('payment_made', 0))
                    booking['is_cancelled'] = int(booking.get('is_cancelled', 0))
                    booking['Status'] = booking.get('Status', 'Pending')
                    booking['PaymentStatus'] = booking.get('PaymentStatus', 'Not Paid')
                    
                    if 'BookingDate' in booking and booking['BookingDate']:
                        booking['BookingDate'] = booking['BookingDate'].strftime('%Y-%m-%d')
                    else:
                        booking['BookingDate'] = 'Not specified'
                        
                    if 'BookingTime' in booking and booking['BookingTime']:
                        from datetime import timedelta
                        if isinstance(booking['BookingTime'], timedelta):
                            hours, remainder = divmod(booking['BookingTime'].seconds, 3600)
                            minutes, _ = divmod(remainder, 60)
                            booking['BookingTime'] = f'{hours:02d}:{minutes:02d}'
                        else:
                            booking['BookingTime'] = booking['BookingTime'].strftime('%H:%M') if booking['BookingTime'] else 'Not specified'
                    else:
                        booking['BookingTime'] = 'Not specified'
                
                cursor.close()
                db.close()
                return jsonify(bookings)
            except Exception as e:
                print(f"Error in get_user_bookings: {str(e)}")
                return jsonify([])
        # For unauthorized users, return empty list instead of error
        return jsonify([])
    except Exception as e:
        print(f"Unexpected error in get_user_bookings: {str(e)}")
        return jsonify([])

@app.route('/api/admin/bookings', methods=['GET'])
def get_admin_bookings():
    # Check admin authentication in multiple ways
    is_admin = (
        'loggedin' in session and 
        (session.get('role') or session.get('is_admin', False) or session.get('id') in get_admin_ids())
    )
    
    if is_admin:
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            cursor.execute('''
                SELECT b.*, s.Name as service_name, 
                       c.Name as customer_name, p.Name as provider_name,
                       (SELECT COUNT(*) FROM Payments pay WHERE pay.B_ID = b.B_ID) as payment_made,
                       (SELECT COUNT(*) FROM Cancellation can WHERE can.B_ID = b.B_ID) as is_cancelled
                FROM Bookings b
                JOIN Services s ON b.S_ID = s.S_ID
                JOIN User c ON b.CustomerID = c.U_ID
                LEFT JOIN User p ON b.ProviderID = p.U_ID
            ''')
            bookings = cursor.fetchall()
            
            # Set default values and handle datetime
            for booking in bookings:
                booking['payment_made'] = booking.get('payment_made', 0)
                booking['is_cancelled'] = booking.get('is_cancelled', 0)
                booking['Status'] = booking.get('Status', 'Pending')
                
                if 'BookingDate' in booking and booking['BookingDate']:
                    booking['BookingDate'] = booking['BookingDate'].strftime('%Y-%m-%d')
                else:
                    booking['BookingDate'] = 'Not specified'
                    
                if 'BookingTime' in booking and booking['BookingTime']:
                    from datetime import timedelta
                    if isinstance(booking['BookingTime'], timedelta):
                        hours, remainder = divmod(booking['BookingTime'].seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        booking['BookingTime'] = f'{hours:02d}:{minutes:02d}'
                    else:
                        booking['BookingTime'] = booking['BookingTime'].strftime('%H:%M') if booking['BookingTime'] else 'Not specified'
                else:
                    booking['BookingTime'] = 'Not specified'
            
            cursor.close()
            db.close()
            return jsonify(bookings)
        except Exception as e:
            print(f"Error in get_admin_bookings: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/admin/providers', methods=['GET'])
def get_service_providers():
    # Check admin authentication in multiple ways
    is_admin = (
        'loggedin' in session and 
        (session.get('role') or session.get('is_admin', False) or session.get('id') in get_admin_ids())
    )
    
    if is_admin:
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get all service providers, not just pending ones
            cursor.execute('''
                SELECT u.*, sp.Specialization, sp.SP_ID, sp.Status
                FROM User u
                JOIN ServiceProvider sp ON u.U_ID = sp.U_ID
            ''')
            
            providers = cursor.fetchall()
            cursor.close()
            db.close()
            return jsonify(providers)
        except Exception as e:
            print(f"Error in get_service_providers: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/bookings', methods=['POST'])
def create_booking():
    if 'loggedin' in session and session.get('user_type') == 'Customer':
        try:
            data = request.json
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get a provider for this service
            cursor.execute('''
                SELECT sp.U_ID 
                FROM ServiceProvider sp
                JOIN User u ON sp.U_ID = u.U_ID
                WHERE sp.Status = 'Approved' 
                LIMIT 1
            ''')
            provider = cursor.fetchone()
            
            if not provider:
                return jsonify({'error': 'No service providers available'}), 400
                
            cursor.execute('''
                INSERT INTO Bookings (CustomerID, ProviderID, S_ID, BookingDate, BookingTime, Status)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (session['id'], provider['U_ID'], data['service_id'], 
                data['date'], data['time'], 'Pending'))
            
            # Get the created booking ID
            booking_id = cursor.lastrowid
            
            # Create a notification for the user
            try:
                cursor.execute('''
                    INSERT INTO Notifications (U_ID, Message)
                    VALUES (%s, %s)
                ''', (session['id'], 'Your booking has been created. Please complete payment to confirm.'))
            except Exception as e:
                print(f"Error creating notification: {str(e)}")
                
            # Create a notification for the provider
            try:
                cursor.execute('''
                    INSERT INTO Notifications (U_ID, Message)
                    VALUES (%s, %s)
                ''', (provider['U_ID'], f'New booking from {session["name"]} is pending payment.'))
            except Exception as e:
                print(f"Error creating provider notification: {str(e)}")
            
            db.commit()
            
            cursor.close()
            db.close()
            
            return jsonify({
                'message': 'Booking created successfully. Please complete payment to confirm.', 
                'booking_id': booking_id,
                'status': 'Pending'
            })
        except Exception as e:
            print(f"Error in create_booking: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/bookings/<int:booking_id>', methods=['DELETE'])
def cancel_booking(booking_id):
    if 'loggedin' in session:
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Check if booking belongs to current user
            if session.get('user_type') == 'Customer':
                cursor.execute('SELECT * FROM Bookings WHERE B_ID = %s AND CustomerID = %s', 
                            (booking_id, session['id']))
            elif session.get('user_type') == 'ServiceProvider':
                cursor.execute('SELECT * FROM Bookings WHERE B_ID = %s AND ProviderID = %s', 
                            (booking_id, session['id']))
            elif session.get('role'):
                cursor.execute('SELECT * FROM Bookings WHERE B_ID = %s', (booking_id,))
            
            booking = cursor.fetchone()
            
            if booking:
                cursor.execute('UPDATE Bookings SET Status = %s WHERE B_ID = %s', 
                            ('Cancelled', booking_id))
                
                # Create a cancellation record
                try:
                    cursor.execute('SELECT COUNT(*) AS count FROM Cancellation WHERE B_ID = %s', (booking_id,))
                    if cursor.fetchone()['count'] == 0:
                        cursor.execute('INSERT INTO Cancellation (B_ID, RefundAmount) VALUES (%s, %s)', 
                                    (booking_id, 0.00))
                except Exception as e:
                    print(f"Error creating cancellation record: {str(e)}")
                
                # Create a notification
                try:
                    cursor.execute('INSERT INTO Notifications (U_ID, Message) VALUES (%s, %s)',
                                (session['id'], f'Booking #{booking_id} has been cancelled.'))
                except Exception as e:
                    print(f"Error creating notification: {str(e)}")
                
                db.commit()
                cursor.close()
                db.close()
                return '', 204
            
            cursor.close()
            db.close()
            return jsonify({'error': 'Booking not found'}), 404
        except Exception as e:
            print(f"Error in cancel_booking: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
def handle_cancel_booking(booking_id):
    """Route to handle the frontend cancel booking request"""
    if 'loggedin' in session:
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Check if booking belongs to current user
            if session.get('user_type') == 'Customer':
                cursor.execute('SELECT * FROM Bookings WHERE B_ID = %s AND CustomerID = %s', 
                            (booking_id, session['id']))
            elif session.get('user_type') == 'ServiceProvider':
                cursor.execute('SELECT * FROM Bookings WHERE B_ID = %s AND ProviderID = %s', 
                            (booking_id, session['id']))
            elif session.get('role'):
                cursor.execute('SELECT * FROM Bookings WHERE B_ID = %s', (booking_id,))
            
            booking = cursor.fetchone()
            
            if booking:
                cursor.execute('UPDATE Bookings SET Status = %s WHERE B_ID = %s', 
                            ('Cancelled', booking_id))
                
                # Check if payment was made for this booking
                cursor.execute('SELECT * FROM Payments WHERE B_ID = %s', (booking_id,))
                payment = cursor.fetchone()
                
                refund_amount = 0.00
                if payment and booking.get('PaymentStatus') == 'Paid':
                    # Set refund amount to the payment amount
                    refund_amount = payment.get('Amount', 0.00)
                
                # Create a cancellation record with refund amount
                try:
                    cursor.execute('SELECT COUNT(*) AS count FROM Cancellation WHERE B_ID = %s', (booking_id,))
                    if cursor.fetchone()['count'] == 0:
                        cursor.execute('INSERT INTO Cancellation (B_ID, RefundAmount, Date) VALUES (%s, %s, NOW())', 
                                    (booking_id, refund_amount))
                except Exception as e:
                    print(f"Error creating cancellation record: {str(e)}")
                
                # Create a notification
                try:
                    cursor.execute('INSERT INTO Notifications (U_ID, Message) VALUES (%s, %s)',
                                (session['id'], f'Booking #{booking_id} has been cancelled. Refund amount: ${refund_amount}'))
                    
                    # Also notify provider if cancelled by customer
                    if session.get('user_type') == 'Customer' and booking.get('ProviderID'):
                        cursor.execute('INSERT INTO Notifications (U_ID, Message) VALUES (%s, %s)',
                                    (booking['ProviderID'], f'Booking #{booking_id} has been cancelled by customer. Refund amount: ${refund_amount}'))
                except Exception as e:
                    print(f"Error creating notification: {str(e)}")
                
                db.commit()
                cursor.close()
                db.close()
                return jsonify({"success": True})
            else:
                cursor.close()
                db.close()
                return jsonify({"success": False, "message": "Booking not found or you don't have permission to cancel it"})
        except Exception as e:
            print(f"Error in cancel_booking: {str(e)}")
            return jsonify({"success": False, "message": str(e)})
    return jsonify({"success": False, "message": "Not logged in"}), 401

# Additional API Routes for the extra tables
@app.route('/api/user/payments', methods=['GET'])
def get_user_payments():
    try:
        if 'loggedin' in session:
            try:
                print(f"Fetching payments for user: {session.get('name')} with type: {session.get('user_type')} and ID: {session.get('id')}")
                
                db = get_db()
                cursor = db.cursor(dictionary=True)
                
                if session.get('user_type') == 'ServiceProvider':
                    # For providers, show all payments for their bookings
                    print("Executing provider-specific payment query...")
                    
                    # First check if there are any bookings for this provider
                    cursor.execute('SELECT COUNT(*) as count FROM Bookings WHERE ProviderID = %s', (session['id'],))
                    booking_count = cursor.fetchone()['count']
                    print(f"Provider has {booking_count} bookings")
                    
                    # Now check if there are any payments associated with these bookings
                    cursor.execute('SELECT COUNT(*) as count FROM Payments p JOIN Bookings b ON p.B_ID = b.B_ID WHERE b.ProviderID = %s', 
                                 (session['id'],))
                    payment_count = cursor.fetchone()['count']
                    print(f"Provider has {payment_count} payments")
                    
                    query = '''
                        SELECT p.*, b.BookingDate, b.BookingTime, s.Name as service_name, u.Name as customer_name
                        FROM Payments p
                        JOIN Bookings b ON p.B_ID = b.B_ID
                        JOIN Services s ON b.S_ID = s.S_ID
                        JOIN User u ON b.CustomerID = u.U_ID
                        WHERE b.ProviderID = %s
                    '''
                    print(f"Executing query: {query}")
                    cursor.execute(query, (session['id'],))
                else:
                    # For customers, show their own payments
                    print("Executing customer-specific payment query...")
                    cursor.execute('''
                        SELECT p.*, b.BookingDate, b.BookingTime, s.Name as service_name, u.Name as customer_name
                        FROM Payments p
                        JOIN Bookings b ON p.B_ID = b.B_ID
                        JOIN Services s ON b.S_ID = s.S_ID
                        JOIN User u ON b.CustomerID = u.U_ID
                        WHERE p.CustomerID = %s OR b.ProviderID = %s
                    ''', (session['id'], session['id']))
                
                payments = cursor.fetchall()
                print(f"Retrieved {len(payments)} payment records")
                
                # Handle null values and datetime serialization
                for payment in payments:
                    payment['PaymentStatus'] = payment.get('PaymentStatus', 'Pending')
                    
                    if 'PaymentDate' in payment and payment['PaymentDate']:
                        payment['PaymentDate'] = payment['PaymentDate'].strftime('%Y-%m-%d')
                    else:
                        payment['PaymentDate'] = 'Not specified'
                        
                    if 'BookingDate' in payment and payment['BookingDate']:
                        payment['BookingDate'] = payment['BookingDate'].strftime('%Y-%m-%d')
                    else:
                        payment['BookingDate'] = 'Not specified'
                        
                    if 'BookingTime' in payment and payment['BookingTime']:
                        from datetime import timedelta
                        if isinstance(payment['BookingTime'], timedelta):
                            hours, remainder = divmod(payment['BookingTime'].seconds, 3600)
                            minutes, _ = divmod(remainder, 60)
                            payment['BookingTime'] = f'{hours:02d}:{minutes:02d}'
                        else:
                            payment['BookingTime'] = payment['BookingTime'].strftime('%H:%M') if payment['BookingTime'] else 'Not specified'
                    else:
                        payment['BookingTime'] = 'Not specified'
                    
                cursor.close()
                db.close()
                return jsonify(payments)
            except Exception as e:
                print(f"Error in get_user_payments: {str(e)}")
                return jsonify([])
        # For unauthorized users, return empty list instead of error
        return jsonify([])
    except Exception as e:
        print(f"Unexpected error in get_user_payments: {str(e)}")
        return jsonify([])

@app.route('/api/user/reviews', methods=['GET'])
def get_user_reviews():
    try:
        if 'loggedin' in session:
            try:
                db = get_db()
                cursor = db.cursor(dictionary=True)
                
                if session.get('user_type') == 'Customer':
                    cursor.execute('''
                        SELECT r.*, u.Name as provider_name
                        FROM Reviews r
                        JOIN User u ON r.ProviderID = u.U_ID
                        WHERE r.CustomerID = %s
                    ''', (session['id'],))
                else:  # Service Provider
                    cursor.execute('''
                        SELECT r.*, u.Name as customer_name
                        FROM Reviews r
                        JOIN User u ON r.CustomerID = u.U_ID
                        WHERE r.ProviderID = %s
                    ''', (session['id'],))
                
                reviews = cursor.fetchall()
                
                # Handle datetime serialization
                for review in reviews:
                    if 'Timestamp' in review and review['Timestamp']:
                        review['Timestamp'] = review['Timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        review['Timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.close()
                db.close()
                return jsonify(reviews)
            except Exception as e:
                print(f"Error in get_user_reviews: {str(e)}")
                return jsonify([])
        # For unauthorized users, return empty list instead of error
        return jsonify([])
    except Exception as e:
        print(f"Unexpected error in get_user_reviews: {str(e)}")
        return jsonify([])

@app.route('/api/user/notifications', methods=['GET'])
def get_user_notifications():
    try:
        if 'loggedin' in session:
            try:
                db = get_db()
                cursor = db.cursor(dictionary=True)
                
                cursor.execute('''
                    SELECT * FROM Notifications 
                    WHERE U_ID = %s 
                    ORDER BY Timestamp DESC
                ''', (session['id'],))
                
                notifications = cursor.fetchall()
                
                # Handle datetime serialization
                for notification in notifications:
                    if 'Timestamp' in notification and notification['Timestamp']:
                        notification['Timestamp'] = notification['Timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        notification['Timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.close()
                db.close()
                return jsonify(notifications)
            except Exception as e:
                print(f"Error in get_user_notifications: {str(e)}")
                return jsonify([])
        # For unauthorized users, return empty list instead of error
        return jsonify([])
    except Exception as e:
        print(f"Unexpected error in get_user_notifications: {str(e)}")
        return jsonify([])

@app.route('/api/notifications/count', methods=['GET'])
def get_notification_count():
    """Get the count of unread notifications for the current user"""
    if 'loggedin' in session:
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            cursor.execute('''
                SELECT COUNT(*) as count FROM Notifications 
                WHERE U_ID = %s AND IsRead = 0
            ''', (session['id'],))
            
            result = cursor.fetchone()
            count = result['count'] if result and 'count' in result else 0
            
            cursor.close()
            db.close()
            return jsonify({'count': count})
        except Exception as e:
            print(f"Error in get_notification_count: {str(e)}")
            return jsonify({'count': 0})
    return jsonify({'count': 0})

@app.route('/api/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    """Mark notifications as read"""
    if 'loggedin' in session:
        try:
            db = get_db()
            cursor = db.cursor()
            
            cursor.execute('''
                UPDATE Notifications 
                SET IsRead = 1 
                WHERE U_ID = %s
            ''', (session['id'],))
            
            db.commit()
            cursor.close()
            db.close()
            return jsonify({'message': 'Notifications marked as read'})
        except Exception as e:
            print(f"Error marking notifications as read: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/user/invoices', methods=['GET'])
def get_user_invoices():
    try:
        if 'loggedin' in session:
            try:
                db = get_db()
                cursor = db.cursor(dictionary=True)
                
                if session.get('user_type') == 'Customer':
                    cursor.execute('''
                        SELECT i.*, b.BookingDate, s.Name as service_name, p.Name as provider_name
                        FROM Invoices i
                        JOIN Bookings b ON i.B_ID = b.B_ID
                        JOIN Services s ON b.S_ID = s.S_ID
                        JOIN User p ON b.ProviderID = p.U_ID
                        WHERE b.CustomerID = %s
                    ''', (session['id'],))
                else:  # Service Provider
                    cursor.execute('''
                        SELECT i.*, b.BookingDate, s.Name as service_name, c.Name as customer_name
                        FROM Invoices i
                        JOIN Bookings b ON i.B_ID = b.B_ID
                        JOIN Services s ON b.S_ID = s.S_ID
                        JOIN User c ON b.CustomerID = c.U_ID
                        WHERE b.ProviderID = %s
                    ''', (session['id'],))
                
                invoices = cursor.fetchall()
                
                # Handle datetime serialization
                for invoice in invoices:
                    if 'InvoiceDate' in invoice and invoice['InvoiceDate']:
                        invoice['InvoiceDate'] = invoice['InvoiceDate'].strftime('%Y-%m-%d')
                    else:
                        invoice['InvoiceDate'] = 'Not specified'
                        
                    if 'BookingDate' in invoice and invoice['BookingDate']:
                        invoice['BookingDate'] = invoice['BookingDate'].strftime('%Y-%m-%d')
                    else:
                        invoice['BookingDate'] = 'Not specified'
                
                cursor.close()
                db.close()
                return jsonify(invoices)
            except Exception as e:
                print(f"Error in get_user_invoices: {str(e)}")
                return jsonify([])
        # For unauthorized users, return empty list instead of error
        return jsonify([])
    except Exception as e:
        print(f"Unexpected error in get_user_invoices: {str(e)}")
        return jsonify([])

@app.route('/api/bookings/<int:booking_id>/cancellation', methods=['GET'])
def get_booking_cancellation(booking_id):
    if 'loggedin' in session:
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            cursor.execute('''
                SELECT *
                FROM Cancellation
                WHERE B_ID = %s
            ''', (booking_id,))
            
            cancellation = cursor.fetchone()
            cursor.close()
            db.close()
            
            if cancellation:
                return jsonify(cancellation)
            return jsonify({'error': 'No cancellation found'}), 404
        except Exception as e:
            print(f"Error in get_booking_cancellation: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

# Reviews API
@app.route('/api/reviews', methods=['POST'])
def add_review():
    if 'loggedin' in session and session.get('user_type') == 'Customer':
        try:
            data = request.json
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            cursor.execute('''
                INSERT INTO Reviews (CustomerID, ProviderID, Rating, Comments)
                VALUES (%s, %s, %s, %s)
            ''', (session['id'], data['provider_id'], data['rating'], data['comments']))
            
            db.commit()
            cursor.close()
            db.close()
            return jsonify({'message': 'Review added successfully'})
        except Exception as e:
            print(f"Error in add_review: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

# Payments API
@app.route('/process_payment/<int:booking_id>', methods=['POST'])
def process_payment(booking_id):
    if 'loggedin' in session and session.get('user_type') == 'Customer':
        try:
            # Get form data values with defaults
            payment_method = request.form.get('payment_method', 'Credit Card')
            amount = request.form.get('amount')
            
            print(f"Processing payment for booking #{booking_id} with method {payment_method}, amount {amount}")
            
            # Map payment method to allowed ENUM values
            payment_method_map = {
                'credit_card': 'Credit Card',
                'debit_card': 'Debit Card',
                'paypal': 'Credit Card',  # Map PayPal to Credit Card since it's not in the ENUM
                'bank_transfer': 'Net Banking'  # Map bank_transfer to Net Banking
            }
            
            # Use mapped value or default to Credit Card if not found
            mapped_payment_method = payment_method_map.get(payment_method, 'Credit Card')
            
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get booking details
            cursor.execute('''
                SELECT b.*, s.Name as service_name, s.Price, b.ProviderID
                FROM Bookings b
                JOIN Services s ON b.S_ID = s.S_ID
                WHERE b.B_ID = %s AND b.CustomerID = %s
            ''', (booking_id, session['id']))
            
            booking = cursor.fetchone()
            
            if not booking:
                cursor.close()
                db.close()
                return jsonify({"success": False, "message": "Booking not found or does not belong to you"})
            
            # Check if payment already exists
            cursor.execute('''
                SELECT * FROM Payments WHERE B_ID = %s
            ''', (booking_id,))
            
            existing_payment = cursor.fetchone()
            
            if existing_payment:
                cursor.close()
                db.close()
                return jsonify({"success": False, "message": "Payment already processed for this booking"})
            
            # Process payment - use booking price if no amount provided
            if not amount:
                amount = booking['Price']
            payment_date = datetime.now().strftime('%Y-%m-%d')
            
            # Insert payment with ProviderID for easier earnings calculations
            cursor.execute('''
                INSERT INTO Payments (B_ID, CustomerID, Amount, PaymentDate, PaymentMethod, PaymentStatus, ProviderID)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (booking_id, session['id'], amount, payment_date, mapped_payment_method, 'Success', booking['ProviderID']))
            
            payment_id = cursor.lastrowid
            
            # Update booking status to Confirmed and make sure PaymentStatus is Paid
            cursor.execute('''
                UPDATE Bookings
                SET Status = 'Confirmed', PaymentStatus = 'Paid'
                WHERE B_ID = %s
            ''', (booking_id,))
            
            # Verify the update was successful by reading back the record
            cursor.execute('''
                SELECT Status, PaymentStatus FROM Bookings WHERE B_ID = %s
            ''', (booking_id,))
            updated_booking = cursor.fetchone()
            print(f"Updated booking status: {updated_booking}")
            
            # Create invoice - use U_ID and B_ID instead of P_ID
            try:
                cursor.execute('''
                    INSERT INTO Invoices (U_ID, B_ID, Amount, Date)
                    VALUES (%s, %s, %s, %s)
                ''', (session['id'], booking_id, amount, payment_date))
                
                invoice_id = cursor.lastrowid
                
                # Create notification for customer
                cursor.execute('''
                    INSERT INTO Notifications (U_ID, Message)
                    VALUES (%s, %s)
                ''', (session['id'], f'Your payment of ${amount} for booking #{booking_id} was successful. Invoice #{invoice_id} has been generated.'))
                
                # Notify provider
                cursor.execute('''
                    INSERT INTO Notifications (U_ID, Message)
                    VALUES (%s, %s)
                ''', (booking['ProviderID'], f'Payment received for booking #{booking_id}. Amount: ${amount}'))
                
                # Make sure to commit all changes
                db.commit()
                
                cursor.close()
                db.close()
                
                return jsonify({"success": True, "message": "Payment processed successfully"})
            except Exception as e:
                print(f"Error creating invoice: {str(e)}")
                # Still return success since payment was processed, even if invoice creation failed
                db.commit()
                cursor.close()
                db.close()
                return jsonify({"success": True, "message": "Payment processed, but invoice creation failed"})
                
        except Exception as e:
            print(f"Error processing payment: {str(e)}")
            return jsonify({"success": False, "message": f"Error processing payment: {str(e)}"})
    return jsonify({"success": False, "message": "Unauthorized"}), 401

@app.route('/make_payment/<int:booking_id>', methods=['GET'])
def make_payment(booking_id):
    if 'loggedin' in session and session.get('user_type') == 'Customer':
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get booking details
            cursor.execute('''
                SELECT b.*, s.Name as service_name, s.Price, u.Name as provider_name
                FROM Bookings b
                JOIN Services s ON b.S_ID = s.S_ID
                JOIN User u ON b.ProviderID = u.U_ID
                WHERE b.B_ID = %s AND b.CustomerID = %s
            ''', (booking_id, session['id']))
            
            booking = cursor.fetchone()
            
            if not booking:
                cursor.close()
                db.close()
                flash('Booking not found or does not belong to you', 'error')
                return redirect(url_for('user_dashboard'))
            
            # Check if payment already exists
            cursor.execute('''
                SELECT * FROM Payments WHERE B_ID = %s
            ''', (booking_id,))
            
            existing_payment = cursor.fetchone()
            
            if existing_payment:
                cursor.close()
                db.close()
                flash('Payment already processed for this booking', 'info')
                return redirect(url_for('user_dashboard'))
            
            cursor.close()
            db.close()
            
            return render_template('payment.html', booking=booking, now=int(time.time()))
        except Exception as e:
            print(f"Error loading payment page: {str(e)}")
            flash('Error loading payment page', 'error')
            return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/invoice/<int:invoice_id>', methods=['GET'])
def view_invoice_by_id(invoice_id):
    if 'loggedin' not in session:
        flash('Please log in to view invoices', 'error')
        return redirect(url_for('login'))
    
    user_id = session.get('id')
    user_type = session.get('user_type')
    
    cursor = None
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Query invoice information directly
        cursor.execute('''
            SELECT i.*, b.*, s.Name as service_name, s.Price, 
                   c.Name as customer_name, c.Email as customer_email,
                   pr.Name as provider_name
            FROM Invoices i
            JOIN Bookings b ON i.B_ID = b.B_ID
            JOIN Services s ON b.S_ID = s.S_ID
            JOIN User c ON b.CustomerID = c.U_ID
            JOIN User pr ON b.ProviderID = pr.U_ID
            WHERE i.I_ID = %s
        ''', (invoice_id,))
        
        invoice_info = cursor.fetchone()
        
        if not invoice_info:
            # Fallback to try finding by Payment ID
            cursor.execute('''
                SELECT p.*, b.*, s.Name as service_name, s.Price, 
                       c.Name as customer_name, c.Email as customer_email,
                       pr.Name as provider_name, i.I_ID as InvoiceID, i.Date as InvoiceDate
                FROM Payments p
                JOIN Bookings b ON p.B_ID = b.B_ID
                JOIN Services s ON b.S_ID = s.S_ID
                JOIN User c ON b.CustomerID = c.U_ID
                JOIN User pr ON b.ProviderID = pr.U_ID
                LEFT JOIN Invoices i ON p.B_ID = i.B_ID
                WHERE p.P_ID = %s
            ''', (invoice_id,))
            
            invoice_info = cursor.fetchone()
        
        if not invoice_info:
            cursor.close()
            conn.close()
            flash('Invoice not found', 'error')
            return redirect(url_for('user_dashboard'))
        
        # Check if user has permission to view this invoice
        if (invoice_info.get('CustomerID') != user_id and 
            invoice_info.get('ProviderID') != user_id and 
            session.get('role') is None):
            cursor.close()
            conn.close()
            flash('You do not have permission to view this invoice', 'error')
            return redirect(url_for('user_dashboard'))
        
        # Format dates
        if invoice_info.get('PaymentDate'):
            invoice_info['payment_date'] = invoice_info['PaymentDate'].strftime('%Y-%m-%d')
        elif invoice_info.get('Date'):
            invoice_info['payment_date'] = invoice_info['Date'].strftime('%Y-%m-%d')
        else:
            invoice_info['payment_date'] = datetime.now().strftime('%Y-%m-%d')
            
        if invoice_info.get('BookingDate'):
            invoice_info['booking_date'] = invoice_info['BookingDate'].strftime('%Y-%m-%d')
        else:
            invoice_info['booking_date'] = 'Not specified'
            
        if invoice_info.get('BookingTime'):
            from datetime import timedelta
            if isinstance(invoice_info['BookingTime'], timedelta):
                hours, remainder = divmod(invoice_info['BookingTime'].seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                invoice_info['booking_time'] = f'{hours:02d}:{minutes:02d}'
            else:
                invoice_info['booking_time'] = invoice_info['BookingTime'].strftime('%H:%M') if invoice_info['BookingTime'] else 'Not specified'
        else:
            invoice_info['booking_time'] = 'Not specified'
        
        # Generate invoice number if not available
        invoice_number = invoice_info.get('InvoiceID', invoice_info.get('I_ID', f'INV-{invoice_id}-{user_id}'))
        
        cursor.close()
        conn.close()
        
        return render_template('invoice.html', 
                              payment=invoice_info,
                              invoice_number=invoice_number)
    except Exception as e:
        print(f"Error viewing invoice: {str(e)}")
        flash('Error viewing invoice', 'error')
        return redirect(url_for('user_dashboard'))

@app.route('/api/invoices', methods=['GET'])
def get_invoices():
    if 'loggedin' not in session:
        return jsonify({"error": "Authentication required"}), 401
    
    user_id = session.get('id')
    user_type = session.get('user_type')
    
    cursor = None
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        if session.get('role'):  # Admin
            cursor.execute("SELECT * FROM Invoices")
        elif user_type == 'ServiceProvider':
            cursor.execute("""
                SELECT i.* FROM Invoices i 
                JOIN Bookings b ON i.B_ID = b.B_ID 
                WHERE b.ProviderID = %s
            """, (user_id,))
        else:  # Customer
            cursor.execute("""
                SELECT i.* FROM Invoices i 
                JOIN Bookings b ON i.B_ID = b.B_ID 
                WHERE b.CustomerID = %s
            """, (user_id,))
            
        invoices = cursor.fetchall()
        return jsonify(invoices)
    
    except Exception as e:
        print(f"Error retrieving invoices: {str(e)}")
        return jsonify({"error": "Failed to retrieve invoices"}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/debug/reset_payment/<int:booking_id>', methods=['GET'])
def debug_reset_payment(booking_id):
    """Debug route to reset a booking's payment status"""
    if 'loggedin' in session:
        try:
            db = get_db()
            cursor = db.cursor()
            
            # Reset the booking payment status
            cursor.execute('''
                UPDATE Bookings
                SET PaymentStatus = 'Not Paid'
                WHERE B_ID = %s
            ''', (booking_id,))
            
            # Also delete any existing payment records
            cursor.execute('DELETE FROM Payments WHERE B_ID = %s', (booking_id,))
            cursor.execute('DELETE FROM Invoices WHERE B_ID = %s', (booking_id,))
            
            db.commit()
            cursor.close()
            db.close()
            
            return jsonify({"success": True, "message": f"Payment status for booking #{booking_id} has been reset"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})
    return jsonify({"success": False, "message": "Unauthorized"}), 401

@app.route('/api/booking/<int:booking_id>/status', methods=['GET'])
def get_booking_status(booking_id):
    """Get the current status of a booking, including payment status"""
    if 'loggedin' in session:
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get booking with payment status and service details
            if session.get('user_type') == 'Customer':
                cursor.execute('''
                    SELECT b.*, s.Name as service_name, s.Price,
                           (SELECT COUNT(*) FROM Payments p WHERE p.B_ID = b.B_ID) as payment_made,
                           (SELECT COUNT(*) FROM Cancellation c WHERE c.B_ID = b.B_ID) as is_cancelled
                    FROM Bookings b
                    JOIN Services s ON b.S_ID = s.S_ID
                    WHERE b.B_ID = %s AND b.CustomerID = %s
                ''', (booking_id, session['id']))
            else:  # Service Provider
                cursor.execute('''
                    SELECT b.*, s.Name as service_name, s.Price,
                           (SELECT COUNT(*) FROM Payments p WHERE p.B_ID = b.B_ID) as payment_made,
                           (SELECT COUNT(*) FROM Cancellation c WHERE c.B_ID = b.B_ID) as is_cancelled
                    FROM Bookings b
                    JOIN Services s ON b.S_ID = s.S_ID
                    WHERE b.B_ID = %s AND b.ProviderID = %s
                ''', (booking_id, session['id']))
            
            fetched_booking = cursor.fetchone()
            cursor.close()
            db.close()
            
            if fetched_booking:
                # Create a serializable booking object
                booking = {}
                
                # Process each key/value pair
                for key, value in fetched_booking.items():
                    if key == 'BookingTime' and isinstance(value, timedelta):
                        # Convert timedelta to string
                        hours, remainder = divmod(value.seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        booking[key] = f"{hours:02d}:{minutes:02d}"
                    elif key == 'BookingDate' and isinstance(value, datetime):
                        # Convert date to string
                        booking[key] = value.strftime('%Y-%m-%d')
                    elif key == 'Price' and value is not None:
                        # Ensure price is a float
                        booking[key] = float(value)
                    else:
                        # Keep other values as-is
                        booking[key] = value
                
                # Add derived fields
                booking['payment_made'] = int(fetched_booking.get('payment_made', 0))
                booking['is_cancelled'] = int(fetched_booking.get('is_cancelled', 0))
                booking['Status'] = fetched_booking.get('Status', 'Pending')
                booking['PaymentStatus'] = fetched_booking.get('PaymentStatus', 'Not Paid')
                
                # Return the serializable booking
                return jsonify(booking)
            
            return jsonify({'error': 'Booking not found'}), 404
        except Exception as e:
            print(f"Error in get_booking_status: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/force_update_payment/<int:booking_id>', methods=['GET'])
def force_update_payment(booking_id):
    """Force update a booking's payment status to Paid after payment processing"""
    if 'loggedin' in session:
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # First check if this is a valid booking for this user
            if session.get('user_type') == 'Customer':
                cursor.execute('SELECT * FROM Bookings WHERE B_ID = %s AND CustomerID = %s', 
                            (booking_id, session['id']))
            else:
                cursor.execute('SELECT * FROM Bookings WHERE B_ID = %s AND ProviderID = %s', 
                            (booking_id, session['id']))
                
            booking = cursor.fetchone()
            if not booking:
                cursor.close()
                db.close()
                return jsonify({"success": False, "message": "Booking not found or unauthorized"}), 404
            
            # Check if payment exists
            cursor.execute('SELECT * FROM Payments WHERE B_ID = %s', (booking_id,))
            payment = cursor.fetchone()
            
            if payment:
                # Update booking status to reflect payment
                cursor.execute('''
                    UPDATE Bookings
                    SET Status = 'Confirmed', PaymentStatus = 'Paid'
                    WHERE B_ID = %s
                ''', (booking_id,))
                
                db.commit()
                result = {"success": True, "message": "Payment status updated", "status": "Paid"}
            else:
                result = {"success": False, "message": "No payment record found", "status": booking.get('PaymentStatus', 'Not Paid')}
            
            cursor.close()
            db.close()
            return jsonify(result)
        except Exception as e:
            print(f"Error force-updating payment: {str(e)}")
            return jsonify({"success": False, "message": str(e)}), 500
    return jsonify({"success": False, "message": "Unauthorized"}), 401

# API Routes for Bookings and Payments
@app.route('/api/bookings/<int:booking_id>', methods=['GET'])
def get_booking(booking_id):
    if 'loggedin' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    print(f"API request for booking ID: {booking_id} by user ID: {session.get('id')}")
    
    try:
        # Create cursor with get_db instead of mysql.connection
        db = get_db()
        cursor = db.cursor(dictionary=True)
        booking = None
        
        # For customers, only return their own bookings
        if session['user_type'] == 'Customer':
            query = '''
                SELECT b.B_ID as id, b.BookingDate as booking_date, b.BookingTime as booking_time, 
                       b.Status as status, s.Name as service_name, s.Price as price,
                       u.Name as provider_name
                FROM Bookings b
                JOIN Services s ON b.S_ID = s.S_ID
                LEFT JOIN User u ON b.ProviderID = u.U_ID
                WHERE b.B_ID = %s AND b.CustomerID = %s
            '''
            print(f"Executing query for customer: {query}")
            cursor.execute(query, (booking_id, session['id']))
            booking = cursor.fetchone()
        # For service providers, return bookings for their services
        elif session['user_type'] == 'ServiceProvider':
            query = '''
                SELECT b.B_ID as id, b.BookingDate as booking_date, b.BookingTime as booking_time, 
                       b.Status as status, s.Name as service_name, s.Price as price,
                       u2.Name as customer_name
                FROM Bookings b
                JOIN Services s ON b.S_ID = s.S_ID
                LEFT JOIN User u2 ON b.CustomerID = u2.U_ID
                WHERE b.B_ID = %s AND b.ProviderID = %s
            '''
            print(f"Executing query for provider: {query}")
            cursor.execute(query, (booking_id, session['id']))
            booking = cursor.fetchone()
        
        # If no booking was found and we're in development mode, try a generic query
        if not booking and app.debug:
            print("No booking found with user restrictions, trying generic query in debug mode")
            query = '''
                SELECT b.B_ID as id, b.BookingDate as booking_date, b.BookingTime as booking_time, 
                       b.Status as status, s.Name as service_name, s.Price as price,
                       u.Name as provider_name, u2.Name as customer_name
                FROM Bookings b
                JOIN Services s ON b.S_ID = s.S_ID
                LEFT JOIN User u ON b.ProviderID = u.U_ID
                LEFT JOIN User u2 ON b.CustomerID = u2.U_ID
                WHERE b.B_ID = %s
            '''
            cursor.execute(query, (booking_id,))
            booking = cursor.fetchone()
        
        print(f"Query result: {booking}")
        
        if booking:
            response = {
                'status': 'success',
                'booking': booking
            }
            
            return jsonify(response)
        else:
            return jsonify({'status': 'error', 'message': 'Booking not found'}), 404
    except Exception as e:
        print(f"Error in get_booking: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()

@app.route('/api/payments', methods=['POST'])
def create_payment():
    if 'loggedin' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    booking_id = data.get('booking_id')
    payment_method = data.get('payment_method')
    
    if not booking_id or not payment_method:
        return jsonify({
            'status': 'error',
            'message': 'Missing required fields'
        }), 400
    
    try:
        # Create cursor with get_db
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Get booking details
        cursor.execute('''
            SELECT b.B_ID, b.CustomerID, b.ProviderID, b.Status, s.Price
            FROM Bookings b
            JOIN Services s ON b.S_ID = s.S_ID
            WHERE b.B_ID = %s
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        
        # Check if booking exists and belongs to the user
        if not booking:
            return jsonify({
                'status': 'error',
                'message': 'Booking not found'
            }), 404
        
        if session['user_type'] == 'Customer' and booking['CustomerID'] != session['id']:
            return jsonify({
                'status': 'error',
                'message': 'Unauthorized access to this booking'
            }), 403
        
        # Map payment method from frontend to database values
        payment_method_map = {
            'credit_card': 'Credit Card',
            'debit_card': 'Debit Card',
            'paypal': 'Paypal',  # Map PayPal to Credit Card since it's not in the ENUM
            'bank_transfer': 'Net Banking'  # Map bank_transfer to Net Banking
        }
        
        # Insert payment record
        payment_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO Payments (B_ID, CustomerID, Amount, PaymentDate, PaymentMethod, PaymentStatus)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            booking_id,
            session['id'],
            booking['Price'],
            payment_date,
            payment_method_map.get(payment_method, payment_method),
            'Success'
        ))
        
        payment_id = cursor.lastrowid
        
        # Update booking status
        cursor.execute('''
            UPDATE Bookings SET Status = %s, PaymentStatus = %s WHERE B_ID = %s
        ''', (
            'Confirmed',
            'Paid',
            booking_id
        ))
        
        # Create invoice with U_ID and B_ID
        try:
            cursor.execute('''
                INSERT INTO Invoices (U_ID, B_ID, Amount, Date)
                VALUES (%s, %s, %s, %s)
            ''', (
                session['id'],
                booking_id,
                booking['Price'],
                payment_date[:10]  # Only use the date part
            ))
        except Exception as invoice_err:
            print(f"Error creating invoice: {str(invoice_err)}")
        
        # Create a notification for the provider
        cursor.execute('''
            INSERT INTO Notifications (U_ID, Message)
            VALUES (%s, %s)
        ''', (
            booking['ProviderID'],
            f'Payment received for booking #{booking_id}. Amount: ${booking["Price"]}'
        ))
        
        db.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Payment processed successfully',
            'payment_id': payment_id
        })
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Payment processing failed: {str(e)}'
        }), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()

# Add route for payments.html
@app.route('/payments')
def payments():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    return render_template('payments.html')

# Add route for payment.html - handle both /payment and /make_payment/<id> routes
@app.route('/payment')
@app.route('/payment/<int:booking_id>')
def payment(booking_id=None):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    # Get booking_id either from URL parameter or query string
    if booking_id is None:
        booking_id = request.args.get('id')
    
    print(f"Payment page accessed with booking_id: {booking_id}")
    
    if not booking_id:
        return redirect(url_for('user_dashboard'))
    
    return render_template('payment.html')

@app.route('/debug/booking/<int:booking_id>', methods=['GET'])
def debug_get_booking(booking_id):
    """Debug route to get booking details without user restrictions"""
    try:
        # Connect to DB
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Generic query that doesn't filter by user
        query = '''
            SELECT b.B_ID as id, b.BookingDate as booking_date, b.BookingTime as booking_time, 
                   b.Status as status, b.CustomerID, b.ProviderID,
                   s.Name as service_name, s.Price as price,
                   u.Name as provider_name, u2.Name as customer_name
            FROM Bookings b
            JOIN Services s ON b.S_ID = s.S_ID
            LEFT JOIN User u ON b.ProviderID = u.U_ID
            LEFT JOIN User u2 ON b.CustomerID = u2.U_ID
            WHERE b.B_ID = %s
        '''
        cursor.execute(query, (booking_id,))
        booking = cursor.fetchone()
        
        if booking:
            return jsonify({
                'status': 'success',
                'booking': booking,
                'note': 'This is debug info only, not for production use'
            })
        else:
            return jsonify({
                'status': 'error', 
                'message': 'No booking found with that ID'
            }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()

@app.route('/api/admin/providers/pending', methods=['GET'])
def get_pending_service_providers():
    # Make authentication check more lenient for admin users
    try:
        # Check authentication in different ways
        if 'loggedin' in session and (session.get('role') or session.get('id') in get_admin_ids()):
            print(f"Admin request for pending providers from {session.get('name')}")
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get only pending service providers
            cursor.execute('''
                SELECT u.U_ID, u.Name, u.Email, u.Phone_no, sp.Specialization, sp.Status
                FROM User u
                JOIN ServiceProvider sp ON u.U_ID = sp.U_ID
                WHERE sp.Status = 'Pending'
            ''')
            
            providers = cursor.fetchall()
            cursor.close()
            db.close()
            return jsonify(providers)
        else:
            print(f"Unauthorized admin API access. Session data: loggedin={session.get('loggedin')}, role={session.get('role')}")
            return jsonify({'error': 'Unauthorized'}), 401
    except Exception as e:
        print(f"Error in get_pending_service_providers: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Helper function to get admin IDs from the database
def get_admin_ids():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute('SELECT A_ID FROM Admin')
        admin_ids = [admin['A_ID'] for admin in cursor.fetchall()]
        cursor.close()
        db.close()
        return admin_ids
    except Exception as e:
        print(f"Error getting admin IDs: {str(e)}")
        return []

@app.route('/api/admin/providers/<int:provider_id>/approve', methods=['POST'])
def approve_provider(provider_id):
    # Check admin authentication in multiple ways
    is_admin = (
        'loggedin' in session and 
        (session.get('role') or session.get('is_admin', False) or session.get('id') in get_admin_ids())
    )
    
    if is_admin:
        try:
            admin_id = session.get('id')
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Update provider status to Approved and set ApprovedBy to current admin ID
            cursor.execute('''
                UPDATE ServiceProvider
                SET Status = 'Approved', ApprovedBy = %s
                WHERE U_ID = %s
            ''', (admin_id, provider_id))
            
            # Update User table's ManagedBy field if it exists
            try:
                cursor.execute("SHOW COLUMNS FROM User LIKE 'ManagedBy'")
                if cursor.fetchone():
                    cursor.execute('''
                        UPDATE User
                        SET ManagedBy = %s
                        WHERE U_ID = %s AND UserType = 'ServiceProvider'
                    ''', (admin_id, provider_id))
            except Exception as e:
                print(f"Note: ManagedBy column might not exist in User table: {e}")
            
            # Create notification for the provider with admin name
            admin_name = get_admin_name(admin_id)
            cursor.execute('''
                INSERT INTO Notifications (U_ID, Message)
                VALUES (%s, %s)
            ''', (provider_id, f'Your service provider account has been approved by {admin_name}. You can now receive booking requests.'))
            
            db.commit()
            cursor.close()
            db.close()
            
            return jsonify({'status': 'success', 'message': 'Service provider approved successfully'})
        except Exception as e:
            print(f"Error in approve_provider: {str(e)}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
    return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

@app.route('/api/admin/providers/<int:provider_id>/reject', methods=['POST'])
def reject_provider(provider_id):
    # Check admin authentication in multiple ways
    is_admin = (
        'loggedin' in session and 
        (session.get('role') or session.get('is_admin', False) or session.get('id') in get_admin_ids())
    )
    
    if is_admin:
        try:
            admin_id = session.get('id')
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Update provider status to Rejected and set ApprovedBy to current admin ID
            cursor.execute('''
                UPDATE ServiceProvider
                SET Status = 'Rejected', ApprovedBy = %s
                WHERE U_ID = %s
            ''', (admin_id, provider_id))
            
            # Update User table's ManagedBy field if it exists
            try:
                cursor.execute("SHOW COLUMNS FROM User LIKE 'ManagedBy'")
                if cursor.fetchone():
                    cursor.execute('''
                        UPDATE User
                        SET ManagedBy = %s
                        WHERE U_ID = %s AND UserType = 'ServiceProvider'
                    ''', (admin_id, provider_id))
            except Exception as e:
                print(f"Note: ManagedBy column might not exist in User table: {e}")
            
            # Create notification for the provider with admin name
            admin_name = get_admin_name(admin_id)
            cursor.execute('''
                INSERT INTO Notifications (U_ID, Message)
                VALUES (%s, %s)
            ''', (provider_id, f'Your service provider application has been rejected by {admin_name}. Please contact support for more information.'))
            
            db.commit()
            cursor.close()
            db.close()
            
            return jsonify({'status': 'success', 'message': 'Service provider rejected successfully'})
        except Exception as e:
            print(f"Error in reject_provider: {str(e)}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
    return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

# Provider Service Management Routes
@app.route('/api/provider/services', methods=['GET'])
def get_provider_services():
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get all services for this provider
            cursor.execute('''
                SELECT s.*, 
                       (SELECT COUNT(*) FROM Bookings b WHERE b.S_ID = s.S_ID) as BookingCount
                FROM Services s
                WHERE s.ProviderID = %s
            ''', (session['id'],))
            
            services = cursor.fetchall()
            cursor.close()
            db.close()
            return jsonify(services)
        except Exception as e:
            print(f"Error in get_provider_services: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/provider/services', methods=['POST'])
def add_provider_service():
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        try:
            data = request.json
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Add service with auto-approval
            cursor.execute('''
                INSERT INTO Services (Name, Price, Description, Duration, ProviderID, is_approved) 
                VALUES (%s, %s, %s, %s, %s, 1)
            ''', (
                data['name'], 
                data['price'], 
                data.get('description', ''), 
                data.get('duration', 60),
                session['id']
            ))
            
            # Get the created service ID
            service_id = cursor.lastrowid
            
            # Create a notification for the provider
            cursor.execute('''
                INSERT INTO Notifications (U_ID, Message)
                VALUES (%s, %s)
            ''', (session['id'], 'Your new service has been successfully added.'))
            
            db.commit()
            cursor.close()
            db.close()
            
            return jsonify({'success': True, 'service_id': service_id})
        except Exception as e:
            print(f"Error adding provider service: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False, 'message': 'Unauthorized'}), 401

@app.route('/api/provider/services/<int:service_id>', methods=['GET'])
def get_provider_service(service_id):
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get specific service for this provider
            cursor.execute('''
                SELECT * FROM Services 
                WHERE S_ID = %s AND ProviderID = %s
            ''', (service_id, session['id']))
            
            service = cursor.fetchone()
            cursor.close()
            db.close()
            
            if service:
                return jsonify(service)
            else:
                return jsonify({'error': 'Service not found or not authorized'}), 404
        except Exception as e:
            print(f"Error in get_provider_service: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/provider/services/<int:service_id>', methods=['PUT'])
def update_provider_service(service_id):
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        try:
            data = request.json
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Update service
            cursor.execute('''
                UPDATE Services 
                SET Name = %s, Price = %s, Description = %s, Duration = %s
                WHERE S_ID = %s AND ProviderID = %s
            ''', (
                data['name'], 
                data['price'], 
                data.get('description', ''), 
                data.get('duration', 60),
                service_id,
                session['id']
            ))
            
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Service not found or not authorized'}), 404
                
            db.commit()
            cursor.close()
            db.close()
            
            return jsonify({'success': True})
        except Exception as e:
            print(f"Error updating provider service: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False, 'message': 'Unauthorized'}), 401

@app.route('/api/provider/services/<int:service_id>', methods=['DELETE'])
def delete_provider_service(service_id):
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Check if service has bookings
            cursor.execute('''
                SELECT COUNT(*) as booking_count 
                FROM Bookings
                WHERE S_ID = %s
            ''', (service_id,))
            
            result = cursor.fetchone()
            if result and result['booking_count'] > 0:
                return jsonify({
                    'success': False, 
                    'message': 'Cannot delete service with existing bookings'
                }), 400
            
            # Delete service
            cursor.execute('''
                DELETE FROM Services 
                WHERE S_ID = %s AND ProviderID = %s
            ''', (service_id, session['id']))
            
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Service not found or not authorized'}), 404
                
            db.commit()
            cursor.close()
            db.close()
            
            return jsonify({'success': True})
        except Exception as e:
            print(f"Error deleting provider service: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False, 'message': 'Unauthorized'}), 401

@app.route('/admin/update_schema', methods=['GET'])
def admin_update_schema():
    """Admin-friendly route to update database schema"""
    if 'loggedin' in session and session.get('role'):
        try:
            db = get_db()
            cursor = db.cursor()
            
            updates_made = []
            
            # Try to add ProviderID column if it doesn't exist
            try:
                cursor.execute("SHOW COLUMNS FROM Services LIKE 'ProviderID'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE Services ADD COLUMN ProviderID INT DEFAULT NULL")
                    updates_made.append("Added ProviderID column")
            except Exception as e:
                print(f"Error checking/adding ProviderID column: {str(e)}")
            
            # Try to add is_approved column if it doesn't exist
            try:
                cursor.execute("SHOW COLUMNS FROM Services LIKE 'is_approved'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE Services ADD COLUMN is_approved TINYINT DEFAULT 0")
                    updates_made.append("Added is_approved column")
            except Exception as e:
                print(f"Error checking/adding is_approved column: {str(e)}")
            
            # Try to add Duration column if it doesn't exist
            try:
                cursor.execute("SHOW COLUMNS FROM Services LIKE 'Duration'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE Services ADD COLUMN Duration INT DEFAULT 60")
                    updates_made.append("Added Duration column")
            except Exception as e:
                print(f"Error checking/adding Duration column: {str(e)}")
            
            # Update existing services to be approved by default
            try:
                cursor.execute("UPDATE Services SET is_approved = 1 WHERE is_approved IS NULL OR is_approved = 0")
                updated_rows = cursor.rowcount
                if updated_rows > 0:
                    updates_made.append(f"Set {updated_rows} existing services to approved status")
            except Exception as e:
                print(f"Error updating existing services: {str(e)}")
            
            # Try to add foreign key constraint if it doesn't exist
            try:
                # Check if constraint exists
                cursor.execute("""
                    SELECT COUNT(*) AS cnt
                    FROM information_schema.TABLE_CONSTRAINTS
                    WHERE CONSTRAINT_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'Services'
                    AND CONSTRAINT_NAME = 'fk_services_provider'
                """)
                result = cursor.fetchone()
                if result and result[0] == 0:
                    cursor.execute("""
                        ALTER TABLE Services 
                        ADD CONSTRAINT fk_services_provider 
                        FOREIGN KEY (ProviderID) REFERENCES User(U_ID) 
                        ON DELETE SET NULL
                    """)
                    updates_made.append("Added foreign key constraint")
            except Exception as e:
                print(f"Error adding foreign key constraint: {str(e)}")
            
            db.commit()
            cursor.close()
            db.close()
            
            if updates_made:
                message = "Database schema updated successfully! Changes made:<br>" + "<br>".join(updates_made)
            else:
                message = "Database schema is already up to date. No changes were necessary."
            
            return render_template('admin_dashboard.html', schema_update_message=message)
        except Exception as e:
            error_message = f"Error updating schema: {str(e)}"
            return render_template('admin_dashboard.html', schema_update_error=error_message)
    
    return redirect(url_for('login'))

# Keep the original debug route for backward compatibility
@app.route('/debug/update_schema', methods=['GET'])
def update_schema():
    """Debug route to update database schema"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Try to add ProviderID column if it doesn't exist
        try:
            cursor.execute("SHOW COLUMNS FROM Services LIKE 'ProviderID'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE Services ADD COLUMN ProviderID INT DEFAULT NULL")
                print("Added ProviderID column")
        except Exception as e:
            print(f"ProviderID column might already exist: {str(e)}")
        
        # Try to add is_approved column if it doesn't exist
        try:
            cursor.execute("SHOW COLUMNS FROM Services LIKE 'is_approved'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE Services ADD COLUMN is_approved TINYINT DEFAULT 0")
                print("Added is_approved column")
        except Exception as e:
            print(f"is_approved column might already exist: {str(e)}")
        
        # Try to add Duration column if it doesn't exist
        try:
            cursor.execute("SHOW COLUMNS FROM Services LIKE 'Duration'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE Services ADD COLUMN Duration INT DEFAULT 60")
                print("Added Duration column")
        except Exception as e:
            print(f"Duration column might already exist: {str(e)}")
        
        # Update existing services to be approved by default
        cursor.execute("UPDATE Services SET is_approved = 1 WHERE is_approved IS NULL OR is_approved = 0")
        print(f"Updated {cursor.rowcount} services to approved status")
        
        db.commit()
        cursor.close()
        db.close()
        
        return jsonify({
            'status': 'success',
            'message': 'Database schema updated successfully'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/provider/profile', methods=['GET'])
def get_provider_profile():
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get provider details including specialization
            cursor.execute('''
                SELECT u.*, sp.Specialization, sp.Status
                FROM User u
                JOIN ServiceProvider sp ON u.U_ID = sp.U_ID
                WHERE u.U_ID = %s
            ''', (session['id'],))
            
            provider = cursor.fetchone()
            cursor.close()
            db.close()
            
            if provider:
                return jsonify(provider)
            else:
                return jsonify({'error': 'Provider not found'}), 404
        except Exception as e:
            print(f"Error in get_provider_profile: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/provider/profile', methods=['PUT'])
def update_provider_profile():
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        try:
            data = request.json
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Update User table first
            cursor.execute('''
                UPDATE User
                SET Name = %s, Email = %s, Phone_no = %s
                WHERE U_ID = %s
            ''', (
                data.get('name', ''),
                data.get('email', ''),
                data.get('phone', ''),
                session['id']
            ))
            
            # Update ServiceProvider table
            cursor.execute('''
                UPDATE ServiceProvider
                SET Specialization = %s
                WHERE U_ID = %s
            ''', (
                data.get('specialization', ''),
                session['id']
            ))
            
            db.commit()
            
            # Update session data
            session['name'] = data.get('name', '')
            session['email'] = data.get('email', '')
            session['phone'] = data.get('phone', '')
            
            cursor.close()
            db.close()
            
            return jsonify({
                'success': True,
                'message': 'Profile updated successfully'
            })
        except Exception as e:
            print(f"Error updating provider profile: {str(e)}")
            return jsonify({
                'success': False,
                'message': f"Error updating profile: {str(e)}"
            }), 500
    return jsonify({
        'success': False,
        'message': 'Unauthorized'
    }), 401

@app.route('/api/provider/password', methods=['PUT'])
def update_provider_password():
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        try:
            data = request.json
            current_password = data.get('current_password', '')
            new_password = data.get('new_password', '')
            
            if not current_password or not new_password:
                return jsonify({
                    'success': False,
                    'message': 'Current and new passwords are required'
                }), 400
            
            # Hash passwords
            hashed_current = hash_password(current_password)
            hashed_new = hash_password(new_password)
            
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Verify current password
            cursor.execute('''
                SELECT Password FROM User WHERE U_ID = %s
            ''', (session['id'],))
            
            user = cursor.fetchone()
            
            if not user or user['Password'] != hashed_current:
                cursor.close()
                db.close()
                return jsonify({
                    'success': False,
                    'message': 'Current password is incorrect'
                }), 401
            
            # Update password
            cursor.execute('''
                UPDATE User SET Password = %s WHERE U_ID = %s
            ''', (hashed_new, session['id']))
            
            db.commit()
            cursor.close()
            db.close()
            
            return jsonify({
                'success': True,
                'message': 'Password updated successfully'
            })
        except Exception as e:
            print(f"Error updating provider password: {str(e)}")
            return jsonify({
                'success': False,
                'message': f"Error updating password: {str(e)}"
            }), 500
    return jsonify({
        'success': False,
        'message': 'Unauthorized'
    }), 401

@app.route('/debug/create-test-payment', methods=['GET'])
def create_test_payment():
    """Create a test booking and payment for development purposes.
    Access this endpoint in your browser to create test data."""
    if not app.debug and not app.testing:
        return jsonify({"success": False, "message": "This endpoint is only available in debug mode"}), 403
    
    try:
        # Check if user is logged in as a service provider
        if not session.get('loggedin') or session.get('user_type') != 'ServiceProvider':
            return jsonify({"success": False, "message": "You must be logged in as a service provider to use this endpoint"}), 403
        
        provider_id = session.get('id')
        if not provider_id:
            return jsonify({"success": False, "message": "Provider ID not found in session"}), 400
            
        print(f"Creating test payment for provider ID: {provider_id}, Name: {session.get('name')}")
        
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Get a valid customer
        cursor.execute("SELECT U_ID FROM User WHERE UserType = 'Customer' LIMIT 1")
        customer = cursor.fetchone()
        if not customer:
            return jsonify({"success": False, "message": "No customers found in the database"}), 400
        
        # Get or create a service for this provider
        cursor.execute("SELECT S_ID FROM Services WHERE ProviderID = %s LIMIT 1", (provider_id,))
        service = cursor.fetchone()
        
        # If provider has no services, create one
        if not service:
            cursor.execute('''
                INSERT INTO Services (Name, Price, Description, Duration, ProviderID, is_approved) 
                VALUES (%s, %s, %s, %s, %s, 1)
            ''', ('Test Service', 50.00, 'Test service for payment testing', 60, provider_id))
            db.commit()
            service_id = cursor.lastrowid
            print(f"Created new service with ID: {service_id} for provider")
        else:
            service_id = service['S_ID']
            print(f"Using existing service with ID: {service_id}")
        
        # Create multiple test bookings and payments (3 bookings in different months)
        bookings_data = [
            # Recent booking - this month
            {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'time': '14:00',
                'amount': 50.00,
                'status': 'Confirmed'
            },
            # Last month booking
            {
                'date': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                'time': '10:00',
                'amount': 75.00,
                'status': 'Confirmed'
            },
            # Pending payment
            {
                'date': (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d'),
                'time': '16:00',
                'amount': 100.00,
                'status': 'Pending'
            }
        ]
        
        results = []
        for idx, booking_data in enumerate(bookings_data):
            # Create a test booking
            booking_date = booking_data['date']
            booking_time = booking_data['time']
            
            print(f"Creating booking {idx+1}: Date={booking_date}, Time={booking_time}")
            
            cursor.execute('''
                INSERT INTO Bookings (CustomerID, ProviderID, S_ID, BookingDate, BookingTime, Status, PaymentStatus)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (customer['U_ID'], provider_id, service_id, booking_date, booking_time, 
                  booking_data['status'], 'Paid' if idx < 2 else 'Not Paid'))
            
            booking_id = cursor.lastrowid
            print(f"Created booking with ID: {booking_id}")
            
            # Only create payment for confirmed bookings
            if idx < 2:
                # Create a test payment
                payment_date = (datetime.now() - timedelta(days=idx*30)).strftime('%Y-%m-%d')
                cursor.execute('''
                    INSERT INTO Payments (B_ID, CustomerID, Amount, PaymentDate, PaymentMethod, PaymentStatus, ProviderID)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (booking_id, customer['U_ID'], booking_data['amount'], payment_date, 'Credit Card', 'Success', provider_id))
                
                payment_id = cursor.lastrowid
                print(f"Created payment with ID: {payment_id}")
                
                # Create a test invoice
                cursor.execute('''
                    INSERT INTO Invoices (U_ID, B_ID, Amount, Date)
                    VALUES (%s, %s, %s, %s)
                ''', (customer['U_ID'], booking_id, booking_data['amount'], payment_date))
                
                results.append({
                    "booking_id": booking_id,
                    "payment_id": payment_id,
                    "amount": booking_data['amount']
                })
            else:
                results.append({
                    "booking_id": booking_id,
                    "status": "Pending payment"
                })
        
        db.commit()
        cursor.close()
        db.close()
        
        # Now verify the data was created correctly
        payment_count_check = check_provider_payments(provider_id)
        
        return jsonify({
            "success": True, 
            "message": "Test data created successfully!", 
            "details": {
                "provider_id": provider_id,
                "customer_id": customer['U_ID'],
                "service_id": service_id,
                "bookings_created": len(results),
                "data": results,
                "payment_verification": payment_count_check
            }
        })
    except Exception as e:
        print(f"Error creating test data: {str(e)}")
        return jsonify({"success": False, "message": f"Error creating test data: {str(e)}"}), 500

def check_provider_payments(provider_id):
    """Helper function to verify payments were created correctly"""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Check bookings
        cursor.execute("SELECT COUNT(*) as count FROM Bookings WHERE ProviderID = %s", (provider_id,))
        booking_count = cursor.fetchone()['count']
        
        # Check payments
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM Payments p
            JOIN Bookings b ON p.B_ID = b.B_ID
            WHERE b.ProviderID = %s
        """, (provider_id,))
        payment_count = cursor.fetchone()['count']
        
        # Check direct provider ID in payments
        cursor.execute("SELECT COUNT(*) as count FROM Payments WHERE ProviderID = %s", (provider_id,))
        direct_payment_count = cursor.fetchone()['count']
        
        cursor.close()
        db.close()
        
        return {
            "bookings": booking_count,
            "payments_via_bookings": payment_count,
            "direct_payments": direct_payment_count
        }
    except Exception as e:
        print(f"Error checking provider payments: {str(e)}")
        return {"error": str(e)}

# Add a new route for provider earnings
@app.route('/api/provider/earnings', methods=['GET'])
def get_provider_earnings():
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get total earnings
            cursor.execute('''
                SELECT SUM(p.Amount) as total_earnings
                FROM Payments p
                JOIN Bookings b ON p.B_ID = b.B_ID
                WHERE b.ProviderID = %s AND p.PaymentStatus = 'Success'
            ''', (session['id'],))
            
            total_earnings = cursor.fetchone()
            
            # Get current month earnings
            current_month = datetime.now().strftime('%Y-%m-01')
            cursor.execute('''
                SELECT SUM(p.Amount) as month_earnings
                FROM Payments p
                JOIN Bookings b ON p.B_ID = b.B_ID
                WHERE b.ProviderID = %s 
                AND p.PaymentStatus = 'Success'
                AND p.PaymentDate >= %s
            ''', (session['id'], current_month))
            
            month_earnings = cursor.fetchone()
            
            # Get pending payments
            cursor.execute('''
                SELECT SUM(s.Price) as pending_amount
                FROM Bookings b
                JOIN Services s ON b.S_ID = s.S_ID
                WHERE b.ProviderID = %s 
                AND b.Status = 'Pending'
                AND b.PaymentStatus = 'Not Paid'
            ''', (session['id'],))
            
            pending_amount = cursor.fetchone()
            
            # Get recent payment history
            cursor.execute('''
                SELECT p.P_ID, p.Amount, p.PaymentDate, p.PaymentMethod, p.PaymentStatus,
                       b.B_ID, s.Name as service_name, c.Name as customer_name
                FROM Payments p
                JOIN Bookings b ON p.B_ID = b.B_ID
                JOIN Services s ON b.S_ID = s.S_ID
                JOIN User c ON b.CustomerID = c.U_ID
                WHERE b.ProviderID = %s
                ORDER BY p.PaymentDate DESC
                LIMIT 10
            ''', (session['id'],))
            
            recent_payments = cursor.fetchall()
            
            # Format the payment dates
            for payment in recent_payments:
                if payment.get('PaymentDate'):
                    payment['PaymentDate'] = payment['PaymentDate'].strftime('%Y-%m-%d')
            
            cursor.close()
            db.close()
            
            return jsonify({
                'total_earnings': float(total_earnings.get('total_earnings', 0) or 0),
                'month_earnings': float(month_earnings.get('month_earnings', 0) or 0),
                'pending_amount': float(pending_amount.get('pending_amount', 0) or 0),
                'recent_payments': recent_payments
            })
            
        except Exception as e:
            print(f"Error getting provider earnings: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Unauthorized'}), 401

# Add a new function to get admin's name by ID
def get_admin_name(admin_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        cursor.execute('SELECT Name FROM Admin WHERE A_ID = %s', (admin_id,))
        admin = cursor.fetchone()
        
        cursor.close()
        db.close()
        
        if admin and admin.get('Name'):
            return admin['Name']
        return "Admin"  # Default name if not found
    except Exception as e:
        print(f"Error getting admin name: {str(e)}")
        return "Admin"  # Default on error

# Add a route to get provider earnings data for the dashboard display
@app.route('/api/provider/earnings/dashboard', methods=['GET'])
def get_provider_earnings_dashboard():
    if 'loggedin' in session and session.get('user_type') == 'ServiceProvider':
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            
            # Get total earnings
            cursor.execute('''
                SELECT COALESCE(SUM(p.Amount), 0) as total_earnings
                FROM Payments p
                JOIN Bookings b ON p.B_ID = b.B_ID
                WHERE b.ProviderID = %s AND p.PaymentStatus = 'Success'
            ''', (session['id'],))
            
            result = cursor.fetchone()
            total_earnings = float(result['total_earnings']) if result else 0.00
            
            # Get current month earnings
            current_month = datetime.now().strftime('%Y-%m-01')
            cursor.execute('''
                SELECT COALESCE(SUM(p.Amount), 0) as month_earnings
                FROM Payments p
                JOIN Bookings b ON p.B_ID = b.B_ID
                WHERE b.ProviderID = %s 
                AND p.PaymentStatus = 'Success'
                AND p.PaymentDate >= %s
            ''', (session['id'], current_month))
            
            result = cursor.fetchone()
            month_earnings = float(result['month_earnings']) if result else 0.00
            
            # Get pending payments (from confirmed but unpaid bookings)
            cursor.execute('''
                SELECT COALESCE(SUM(s.Price), 0) as pending_amount
                FROM Bookings b
                JOIN Services s ON b.S_ID = s.S_ID
                WHERE b.ProviderID = %s 
                AND b.Status != 'Cancelled'
                AND b.PaymentStatus = 'Not Paid'
            ''', (session['id'],))
            
            result = cursor.fetchone()
            pending_amount = float(result['pending_amount']) if result else 0.00
            
            cursor.close()
            db.close()
            
            return jsonify({
                'total_earnings': total_earnings,
                'month_earnings': month_earnings,
                'pending_amount': pending_amount
            })
            
        except Exception as e:
            print(f"Error getting provider earnings dashboard: {str(e)}")
            return jsonify({
                'total_earnings': 0.00,
                'month_earnings': 0.00,
                'pending_amount': 0.00,
                'error': str(e)
            })
    return jsonify({
        'total_earnings': 0.00,
        'month_earnings': 0.00,
        'pending_amount': 0.00,
        'error': 'Unauthorized'
    })

if __name__ == '__main__':
    app.debug = True  # Explicitly set debug mode
    app.run(debug=True) 