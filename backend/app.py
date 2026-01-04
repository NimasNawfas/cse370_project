from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import mysql.connector
import os
from datetime import datetime, date, timedelta
import json

# Get the absolute path to templates (one level up)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, 
            template_folder=TEMPLATES_DIR,
            static_folder=STATIC_DIR)

from config import DB_CONFIG, SECRET_KEY
app.secret_key = SECRET_KEY

# ============ CUSTOM JINJA2 FILTERS ============
@app.template_filter('currency')
# ============ CUSTOM JINJA2 FILTERS ============
@app.template_filter('currency')
def currency_format(value):
    """Format as currency (৳1,234.56)"""
    if value is None:
        return "৳0.00"
    try:
        return f"৳{float(value):,.2f}"
    except (ValueError, TypeError):
        return "৳0.00"

@app.template_filter('pad_id')
def pad_id_filter(value):
    """Pad worker ID with zeros (WKR-0001)"""
    if value is None:
        return "WKR-0000"
    try:
        return f"WKR-{int(value):04d}"
    except (ValueError, TypeError):
        return f"WKR-{value}"

@app.template_filter('percentage')
def percentage_filter(value):
    """Format as percentage (95.5%)"""
    if value is None:
        return "0%"
    try:
        return f"{float(value):.1f}%"
    except (ValueError, TypeError):
        return "0%"

@app.template_filter('hours')
def hours_filter(value):
    """Format hours (8.5 hrs)"""
    if value is None:
        return "0 hrs"
    try:
        return f"{float(value):.1f} hrs"
    except (ValueError, TypeError):
        return "0 hrs"

@app.template_filter('date_only')
def date_only_filter(value):
    """Extract date only from datetime"""
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y-%m-%d')
    return str(value)

# ============ END OF CUSTOM FILTERS ============

def get_db_connection():
    """Connect to XAMPP MySQL database"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"❌ Database Connection Error: {err}")
        return None

# ============ LOGIN ============

@app.route('/')
def home():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        db = get_db_connection()
        cursor = db.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT * FROM WORKER WHERE email = %s AND password = %s", 
                      (email, password))
        user = cursor.fetchone()
        cursor.close()
        db.close()
        
        if user:
            session['user_id'] = user['worker_id']
            session['name'] = user['name']
            session['role'] = user['role']
            
            if user['role'] == 'worker':
                return redirect('/worker/dashboard')
            elif user['role'] == 'manager':
                return redirect('/manager/dashboard')
            else:
                return redirect('/admin/dashboard')
        else:
            return render_template('login.html', error="Wrong email or password!")
    
    return render_template('login.html')


# ============ SIGNUP ============
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm = request.form['confirm_password']
        contact = request.form.get('contact', '')
        address = request.form.get('address', '')
        department = request.form.get('department', 'General')
        role = request.form.get('role', 'worker')
        payment = request.form.get('payment_method', 'Cash')
        
        if password != confirm:
            return render_template('signup.html', error="Passwords don't match!")
        
        db = get_db_connection()
        cursor = db.cursor()
        
        try:
            sql = """
            INSERT INTO WORKER (name, email, password, contact, address, 
                              department, role, payment_method, status, joining_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Active', CURDATE())
            """
            
            cursor.execute(sql, (name, email, password, contact, address,
                               department, role, payment))
            db.commit()
            cursor.close()
            db.close()
            
            return redirect('/login')
            
        except mysql.connector.Error:
            cursor.close()
            db.close()
            return render_template('signup.html', error="Email already exists!")
    
    return render_template('signup.html')

# ============ LOGOUT ============
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ============ WORKER ROUTES ============
# ----- Worker Dashboard -----
@app.route('/worker/dashboard')
def worker_dashboard():
    if 'user_id' not in session or session['role'] != 'worker':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get worker data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    worker = cursor.fetchone()
    
    # Today's attendance
    today = date.today().strftime('%Y-%m-%d')
    cursor.execute("SELECT * FROM ATTENDANCE WHERE worker_id=%s AND date=%s", 
                   (session['user_id'], today))
    attendance = cursor.fetchone()
    
    # Recent tasks (5 tasks)
    cursor.execute("""
        SELECT * FROM TASK 
        WHERE worker_id=%s 
        ORDER BY deadline LIMIT 5
    """, (session['user_id'],))
    tasks = cursor.fetchall()
    
    # Recent salary record
    cursor.execute("""
        SELECT * FROM SALARY 
        WHERE worker_id=%s 
        ORDER BY month DESC LIMIT 1
    """, (session['user_id'],))
    latest_salary = cursor.fetchone()
    
    cursor.close()
    db.close()
    
    return render_template('worker/dashboard.html', 
                         worker=worker,
                         attendance=attendance,
                         tasks=tasks,
                         latest_salary=latest_salary,
                         today=today)

# ----- Worker Profile -----
@app.route('/worker/profile')
def worker_profile():
    if 'user_id' not in session or session['role'] != 'worker':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    worker = cursor.fetchone()
    cursor.close()
    db.close()
    
    return render_template('worker/profile.html', worker=worker)

# ----- Update Profile -----
@app.route('/worker/profile/update', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect('/login')
    
    contact = request.form.get('contact')
    address = request.form.get('address')
    
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE WORKER SET contact=%s, address=%s WHERE worker_id=%s", 
                   (contact, address, session['user_id']))
    db.commit()
    cursor.close()
    db.close()
    
    return redirect('/worker/profile')

# ----- Change Password -----
@app.route('/worker/profile/change-password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return redirect('/login')
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if new_password != confirm_password:
        return redirect('/worker/profile?error=password_mismatch')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Verify current password
    cursor.execute("SELECT password FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    worker = cursor.fetchone()
    
    if worker['password'] != current_password:
        cursor.close()
        db.close()
        return redirect('/worker/profile?error=wrong_password')
    
    # Update password
    cursor.execute("UPDATE WORKER SET password=%s WHERE worker_id=%s", 
                   (new_password, session['user_id']))
    db.commit()
    
    cursor.close()
    db.close()
    
    return redirect('/worker/profile?success=password_changed')

# ----- Worker Tasks Page -----
@app.route('/worker/tasks')
def worker_tasks():
    if 'user_id' not in session or session['role'] != 'worker':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    worker = cursor.fetchone()
    
    cursor.execute("SELECT * FROM TASK WHERE worker_id=%s ORDER BY deadline", (session['user_id'],))
    tasks = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('worker/tasks.html', 
                         worker=worker,
                         tasks=tasks,
                         total_tasks=len(tasks),
                         completed_tasks=len([t for t in tasks if t['status'] == 'Completed']),
                         pending_tasks=len([t for t in tasks if t['status'] == 'Pending']))

# ----- Mark Task Complete -----
@app.route('/worker/task/<int:task_id>/complete', methods=['POST'])
def complete_task(task_id):
    if 'user_id' not in session:
        return "Not logged in", 401
    
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE TASK SET status='Completed' WHERE task_id=%s AND worker_id=%s", 
                   (task_id, session['user_id']))
    db.commit()
    cursor.close()
    db.close()
    
    return redirect('/worker/tasks')

# ----- Update Task Status -----
@app.route('/worker/task/<int:task_id>/update-status', methods=['POST'])
def update_task_status(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    status = request.form.get('status')
    
    if status not in ['Pending', 'In Progress', 'Completed', 'Delayed']:
        return jsonify({'error': 'Invalid status'}), 400
    
    db = get_db_connection()
    cursor = db.cursor()
    
    cursor.execute("UPDATE TASK SET status=%s WHERE task_id=%s AND worker_id=%s", 
                   (status, task_id, session['user_id']))
    db.commit()
    
    cursor.close()
    db.close()
    
    return jsonify({'success': True})

# ----- Get Task Details -----
@app.route('/worker/task/<int:task_id>')
def get_task_details(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT t.*, w.name as assigned_by 
        FROM TASK t
        LEFT JOIN WORKER w ON t.worker_id = w.worker_id
        WHERE t.task_id = %s AND t.worker_id = %s
    """, (task_id, session['user_id']))
    task = cursor.fetchone()
    
    cursor.close()
    db.close()
    
    if task:
        return jsonify(task)
    else:
        return jsonify({'error': 'Task not found'}), 404

# ----- Worker Attendance Page -----
@app.route('/worker/attendance')
def worker_attendance():
    if 'user_id' not in session or session['role'] != 'worker':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get worker data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    worker = cursor.fetchone()
    
    # Today's attendance
    today = date.today().strftime('%Y-%m-%d')
    cursor.execute("SELECT * FROM ATTENDANCE WHERE worker_id=%s AND date=%s", 
                   (session['user_id'], today))
    today_attendance = cursor.fetchone()
    
    # Attendance history (last 30 days)
    cursor.execute("""
        SELECT * FROM ATTENDANCE 
        WHERE worker_id = %s 
        ORDER BY date DESC 
        LIMIT 30
    """, (session['user_id'],))
    attendance_history = cursor.fetchall()
    
    # Monthly summary
    cursor.execute("""
        SELECT 
            DATE_FORMAT(date, '%Y-%m') as month,
            COUNT(*) as total_days,
            SUM(attendance_value) as attendance_days,
            AVG(working_hours) as avg_hours
        FROM ATTENDANCE 
        WHERE worker_id = %s 
        GROUP BY DATE_FORMAT(date, '%Y-%m')
        ORDER BY month DESC
        LIMIT 6
    """, (session['user_id'],))
    monthly_summary = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('worker/attendance.html', 
                         worker=worker,
                         today_attendance=today_attendance,
                         attendance_history=attendance_history,
                         monthly_summary=monthly_summary,
                         today=today)

# ----- Attendance Check-in -----
@app.route('/worker/attendance/checkin', methods=['POST'])
def check_in():
    if 'user_id' not in session:
        return "Not logged in", 401
    
    today = date.today().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%H:%M:%S')
    
    db = get_db_connection()
    cursor = db.cursor()
    
    # Check if already checked in
    cursor.execute("SELECT * FROM ATTENDANCE WHERE worker_id=%s AND date=%s", 
                   (session['user_id'], today))
    if cursor.fetchone():
        cursor.close()
        db.close()
        return redirect('/worker/dashboard?error=already_checked_in')
    
    # Insert check-in (0.5 attendance)
    sql = """
    INSERT INTO ATTENDANCE (worker_id, date, check_in, attendance_value)
    VALUES (%s, %s, %s, 0.5)
    """
    cursor.execute(sql, (session['user_id'], today, current_time))
    db.commit()
    cursor.close()
    db.close()
    
    return redirect('/worker/dashboard')

# ----- Attendance Check-out -----
@app.route('/worker/attendance/checkout', methods=['POST'])
def check_out():
    if 'user_id' not in session:
        return "Not logged in", 401
    
    today = date.today().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%H:%M:%S')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get check-in time
    cursor.execute("SELECT check_in FROM ATTENDANCE WHERE worker_id=%s AND date=%s", 
                   (session['user_id'], today))
    check_in_record = cursor.fetchone()
    
    if not check_in_record:
        cursor.close()
        db.close()
        return redirect('/worker/dashboard?error=not_checked_in')
    
    # Calculate working hours - SIMPLE WAY
    # Get check_in as string first
    check_in_str = str(check_in_record['check_in'])
    
    # Parse check_in time (handle timedelta by extracting hours/minutes/seconds)
    if isinstance(check_in_record['check_in'], timedelta):
        td = check_in_record['check_in']
        check_in_seconds = td.seconds
        check_in_hours = check_in_seconds // 3600
        check_in_minutes = (check_in_seconds % 3600) // 60
        check_in_secs = check_in_seconds % 60
        check_in_time = datetime.strptime(f"{check_in_hours:02d}:{check_in_minutes:02d}:{check_in_secs:02d}", '%H:%M:%S')
    else:
        check_in_time = datetime.strptime(check_in_str, '%H:%M:%S')
    
    check_out_time = datetime.strptime(current_time, '%H:%M:%S')
    working_hours = (check_out_time - check_in_time).seconds / 3600
    
    # Update check-out with working hours
    sql = """
    UPDATE ATTENDANCE 
    SET check_out=%s, attendance_value=1.0, working_hours=%s
    WHERE worker_id=%s AND date=%s
    """
    cursor.execute(sql, (current_time, round(working_hours, 2), 
                         session['user_id'], today))
    db.commit()
    
    cursor.close()
    db.close()
    
    return redirect('/worker/dashboard')

# ----- Worker Substitute Page -----
@app.route('/worker/substitute')
def worker_substitute():
    if 'user_id' not in session or session['role'] != 'worker':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get worker data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    worker = cursor.fetchone()
    
    # Get substitute requests made by this worker
    cursor.execute("""
        SELECT sr.*, w.name as substitute_name, w.department 
        FROM SUBSTITUTE_REQUEST sr
        LEFT JOIN WORKER w ON sr.substitute_id = w.worker_id
        WHERE sr.requester_id = %s 
        ORDER BY date DESC
    """, (session['user_id'],))
    my_requests = cursor.fetchall()
    
    # Get requests where this worker is the substitute
    cursor.execute("""
        SELECT sr.*, w.name as requester_name, w.department 
        FROM SUBSTITUTE_REQUEST sr
        JOIN WORKER w ON sr.requester_id = w.worker_id
        WHERE sr.substitute_id = %s 
        ORDER BY date DESC
    """, (session['user_id'],))
    substitute_for = cursor.fetchall()
    
    # Get available substitutes (same department, active, not self)
    cursor.execute("""
        SELECT worker_id, name, department 
        FROM WORKER 
        WHERE department = %s 
        AND status = 'Active'
        AND worker_id != %s
        AND role = 'worker'
        ORDER BY name
    """, (worker['department'], session['user_id']))
    available_substitutes = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('worker/substitute.html',
                         worker=worker,
                         my_requests=my_requests,
                         substitute_for=substitute_for,
                         available_substitutes=available_substitutes)

# ----- Submit Substitute Request -----
@app.route('/worker/substitute/request', methods=['POST'])
def submit_substitute_request():
    if 'user_id' not in session:
        return redirect('/login')
    
    substitute_id = request.form.get('substitute_id')
    date = request.form.get('date')
    hours = request.form.get('hours')
    reason = request.form.get('reason', '')
    
    if not all([substitute_id, date, hours]):
        return redirect('/worker/substitute?error=missing_fields')
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        sql = """
        INSERT INTO SUBSTITUTE_REQUEST 
        (requester_id, substitute_id, date, hours, reason, status, admin_approved)
        VALUES (%s, %s, %s, %s, %s, 'Pending', FALSE)
        """
        cursor.execute(sql, (session['user_id'], substitute_id, date, hours, reason))
        db.commit()
        
        cursor.close()
        db.close()
        
        return redirect('/worker/substitute?success=true')
    except mysql.connector.Error as err:
        cursor.close()
        db.close()
        return redirect(f'/worker/substitute?error={str(err)}')

# ----- Accept Substitute Request -----
@app.route('/worker/substitute/accept/<int:request_id>', methods=['POST'])
def accept_substitute_request(request_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor()
    
    # Check if this worker is the substitute
    cursor.execute("""
        SELECT * FROM SUBSTITUTE_REQUEST 
        WHERE sub_id = %s AND substitute_id = %s
    """, (request_id, session['user_id']))
    
    if cursor.fetchone():
        cursor.execute("""
            UPDATE SUBSTITUTE_REQUEST 
            SET status = 'Accepted' 
            WHERE sub_id = %s
        """, (request_id,))
        db.commit()
    
    cursor.close()
    db.close()
    
    return redirect('/worker/substitute')

# ----- Worker Leave Page -----
@app.route('/worker/leave')
def worker_leave():
    if 'user_id' not in session or session['role'] != 'worker':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get worker data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    worker = cursor.fetchone()
    
    # Get leave balance (placeholder - would come from LEAVE_BALANCE table)
    leave_balance = {
        'casual': 12,
        'sick': 6,
        'annual': 20,
        'taken_this_year': 8
    }
    
    cursor.close()
    db.close()
    
    return render_template('worker/leave.html', 
                         worker=worker,
                         leave_balance=leave_balance)

# ----- Submit Leave Request -----
@app.route('/worker/leave/request', methods=['POST'])
def submit_leave_request():
    if 'user_id' not in session:
        return redirect('/login')
    
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    leave_type = request.form.get('leave_type')
    reason = request.form.get('reason', '')
    
    if not all([start_date, end_date, leave_type]):
        return redirect('/worker/leave?error=missing_fields')
    
    # In a complete system, you would:
    # 1. Validate dates
    # 2. Check leave balance
    # 3. Insert into LEAVE_REQUEST table
    # 4. Send notification to admin
    
    # For now, simulate success
    return redirect('/worker/leave?success=true&type=' + leave_type)

# ----- Worker Salary Page -----
@app.route('/worker/salary')
def worker_salary():
    if 'user_id' not in session or session['role'] != 'worker':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get worker data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    worker = cursor.fetchone()
    
    # Get salary records
    cursor.execute("""
        SELECT * FROM SALARY 
        WHERE worker_id=%s 
        ORDER BY month DESC
    """, (session['user_id'],))
    salaries = cursor.fetchall()
    
    # Calculate summary
    total_earned = sum(salary['total_salary'] or 0 for salary in salaries)
    avg_salary = total_earned / len(salaries) if salaries else 0
    
    # Current month
    current_month = datetime.now().strftime('%Y-%m')
    
    cursor.close()
    db.close()
    
    return render_template('worker/salary.html', 
                         worker=worker,
                         salaries=salaries,
                         total_earned=total_earned,
                         avg_salary=avg_salary,
                         current_month=current_month)

# ----- Worker Performance Page -----
@app.route('/worker/performance')
def worker_performance():
    if 'user_id' not in session or session['role'] != 'worker':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get worker data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    worker = cursor.fetchone()
    
    # Get performance records
    cursor.execute("""
        SELECT * FROM PERFORMANCE 
        WHERE worker_id=%s 
        ORDER BY month DESC
    """, (session['user_id'],))
    performances = cursor.fetchall()
    
    # Current month stats
    current_month = datetime.now().strftime('%Y-%m')
    cursor.execute("""
        SELECT 
            COUNT(*) as days_worked,
            SUM(attendance_value) as total_days,
            AVG(working_hours) as avg_hours,
            SUM(working_hours) as total_hours
        FROM ATTENDANCE 
        WHERE worker_id = %s 
        AND DATE_FORMAT(date, '%Y-%m') = %s
    """, (session['user_id'], current_month))
    current_stats = cursor.fetchone()
    
    cursor.close()
    db.close()
    
    return render_template('worker/performance.html', 
                         worker=worker,
                         performances=performances,
                         current_stats=current_stats,
                         current_month=current_month)

# ============ ADMIN ROUTES ============

# ✅ ADD THIS CONTEXT PROCESSOR - MAKES datetime AVAILABLE IN ALL TEMPLATES
@app.context_processor
def inject_datetime():
    return {'datetime': datetime, 'date': date}

# ----- Admin Dashboard -----
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get admin data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    admin = cursor.fetchone()
    
    # Get total counts
    cursor.execute("SELECT COUNT(*) as total FROM WORKER WHERE role='worker'")
    total_workers = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM WORKER WHERE role='manager'")
    total_managers = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM ATTENDANCE WHERE date=CURDATE()")
    today_attendance = cursor.fetchone()['total']
    
    # Get pending approvals
    cursor.execute("SELECT COUNT(*) as total FROM SUBSTITUTE_REQUEST WHERE admin_approved=FALSE AND status='Accepted'")
    pending_substitutes = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM SALARY WHERE status='Pending'")
    pending_salaries = cursor.fetchone()['total']
    
    # Recent activity
    cursor.execute("""
        SELECT w.name, a.date, a.check_in, a.check_out 
        FROM ATTENDANCE a
        JOIN WORKER w ON a.worker_id = w.worker_id
        WHERE a.date = CURDATE()
        ORDER BY a.check_in DESC
        LIMIT 5
    """)
    recent_attendance = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('admin/dashboard.html',
                         admin=admin,
                         total_workers=total_workers,
                         total_managers=total_managers,
                         today_attendance=today_attendance,
                         pending_substitutes=pending_substitutes,
                         pending_salaries=pending_salaries,
                         recent_attendance=recent_attendance)

# ----- Admin Profile -----
@app.route('/admin/profile')
def admin_profile():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    admin = cursor.fetchone()
    cursor.close()
    db.close()
    
    return render_template('admin/profile.html', admin=admin)

# ----- Update Admin Profile -----
@app.route('/admin/profile/update', methods=['POST'])
def update_admin_profile():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    contact = request.form.get('contact')
    address = request.form.get('address')
    
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE WORKER SET contact=%s, address=%s WHERE worker_id=%s", 
                   (contact, address, session['user_id']))
    db.commit()
    cursor.close()
    db.close()
    
    return redirect('/admin/profile')

# ----- Change Admin Password -----
@app.route('/admin/profile/change-password', methods=['POST'])
def change_admin_password():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if new_password != confirm_password:
        return redirect('/admin/profile?error=password_mismatch')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Verify current password
    cursor.execute("SELECT password FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    admin = cursor.fetchone()
    
    if admin['password'] != current_password:
        cursor.close()
        db.close()
        return redirect('/admin/profile?error=wrong_password')
    
    # Update password
    cursor.execute("UPDATE WORKER SET password=%s WHERE worker_id=%s", 
                   (new_password, session['user_id']))
    db.commit()
    
    cursor.close()
    db.close()
    
    return redirect('/admin/profile?success=password_changed')

# ----- All Workers View -----
@app.route('/admin/all_workers')
def all_workers():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get admin data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    admin = cursor.fetchone()
    
    # Get all workers with their departments
    cursor.execute("""
        SELECT w.*, 
               (SELECT COUNT(*) FROM ATTENDANCE a WHERE a.worker_id = w.worker_id AND MONTH(a.date) = MONTH(CURDATE())) as attendance_days,
               (SELECT SUM(a.working_hours) FROM ATTENDANCE a WHERE a.worker_id = w.worker_id AND MONTH(a.date) = MONTH(CURDATE())) as total_hours
        FROM WORKER w
        WHERE w.role IN ('worker', 'manager')
        ORDER BY w.department, w.name
    """)
    workers = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('admin/all_workers.html',
                         admin=admin,
                         workers=workers)

# ----- View Single Worker Details -----
@app.route('/admin/worker/<int:worker_id>')
def view_worker_details(worker_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get admin data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    admin = cursor.fetchone()
    
    # Get worker details
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (worker_id,))
    worker = cursor.fetchone()
    
    if not worker:
        cursor.close()
        db.close()
        return redirect('/admin/all_workers?error=worker_not_found')
    
    # Get worker attendance (last 30 days)
    cursor.execute("""
        SELECT * FROM ATTENDANCE 
        WHERE worker_id = %s 
        ORDER BY date DESC 
        LIMIT 30
    """, (worker_id,))
    attendance = cursor.fetchall()
    
    # Get worker tasks
    cursor.execute("""
        SELECT * FROM TASK 
        WHERE worker_id = %s 
        ORDER BY deadline
    """, (worker_id,))
    tasks = cursor.fetchall()
    
    # Get worker salary records
    cursor.execute("""
        SELECT * FROM SALARY 
        WHERE worker_id = %s 
        ORDER BY month DESC
    """, (worker_id,))
    salaries = cursor.fetchall()
    
    # Get worker performance
    cursor.execute("""
        SELECT * FROM PERFORMANCE 
        WHERE worker_id = %s 
        ORDER BY month DESC
    """, (worker_id,))
    performances = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('admin/worker_details.html',
                         admin=admin,
                         worker=worker,
                         attendance=attendance,
                         tasks=tasks,
                         salaries=salaries,
                         performances=performances)

# ----- Update Worker Status -----
@app.route('/admin/worker/<int:worker_id>/update-status', methods=['POST'])
def update_worker_status(worker_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    new_status = request.form.get('status')
    
    if new_status not in ['Active', 'On Leave', 'Inactive']:
        return jsonify({'error': 'Invalid status'}), 400
    
    db = get_db_connection()
    cursor = db.cursor()
    
    cursor.execute("UPDATE WORKER SET status=%s WHERE worker_id=%s", 
                   (new_status, worker_id))
    db.commit()
    
    cursor.close()
    db.close()
    
    return jsonify({'success': True, 'new_status': new_status})

# ----- Attendance Reports -----
@app.route('/admin/attendance_reports')
def attendance_reports():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get admin data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    admin = cursor.fetchone()
    
    # Get date range from query params
    start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    
    # Get department-wise attendance summary
    cursor.execute("""
        SELECT 
            w.department,
            COUNT(DISTINCT w.worker_id) as total_workers,
            COUNT(DISTINCT a.worker_id) as workers_present,
            SUM(a.attendance_value) as total_attendance_days,
            AVG(a.working_hours) as avg_hours,
            MIN(a.date) as earliest_date,
            MAX(a.date) as latest_date
        FROM WORKER w
        LEFT JOIN ATTENDANCE a ON w.worker_id = a.worker_id 
            AND a.date BETWEEN %s AND %s
        WHERE w.role = 'worker'
        GROUP BY w.department
        ORDER BY w.department
    """, (start_date, end_date))
    department_summary = cursor.fetchall()
    
    # Get daily attendance count
    cursor.execute("""
        SELECT 
            date,
            COUNT(*) as total_checkins,
            SUM(attendance_value) as total_attendance,
            AVG(working_hours) as avg_hours
        FROM ATTENDANCE
        WHERE date BETWEEN %s AND %s
        GROUP BY date
        ORDER BY date DESC
    """, (start_date, end_date))
    daily_summary = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('admin/attendance_reports.html',
                         admin=admin,
                         department_summary=department_summary,
                         daily_summary=daily_summary,
                         start_date=start_date,
                         end_date=end_date)

# ----- Salary Management -----
@app.route('/admin/salary_management')
def salary_management():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get admin data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    admin = cursor.fetchone()
    
    # Get month from query params (default current month)
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    
    # Get all salary records for the month
    cursor.execute("""
        SELECT s.*, w.name, w.department, w.contact
        FROM SALARY s
        JOIN WORKER w ON s.worker_id = w.worker_id
        WHERE s.month = %s
        ORDER BY w.department, w.name
    """, (month,))
    salaries = cursor.fetchall()
    
    # Get workers without salary records for this month
    cursor.execute("""
        SELECT w.*
        FROM WORKER w
        WHERE w.role = 'worker' 
        AND w.status = 'Active'
        AND NOT EXISTS (
            SELECT 1 FROM SALARY s 
            WHERE s.worker_id = w.worker_id 
            AND s.month = %s
        )
        ORDER BY w.department, w.name
    """, (month,))
    workers_without_salary = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('admin/salary_management.html',
                         admin=admin,
                         salaries=salaries,
                         workers_without_salary=workers_without_salary,
                         current_month=month)

# ----- Create Salary Record -----
@app.route('/admin/salary/create', methods=['POST'])
def create_salary():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    worker_id = request.form.get('worker_id')
    month = request.form.get('month')
    base_salary = float(request.form.get('base_salary', 0))
    extra_hours = int(request.form.get('extra_hours', 0))
    
    # Calculate bonus (50 per extra hour)
    bonus_amount = extra_hours * 50
    total_salary = base_salary + bonus_amount
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        sql = """
        INSERT INTO SALARY (worker_id, month, base_salary, extra_hours, bonus_amount, total_salary, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'Draft')
        """
        cursor.execute(sql, (worker_id, month, base_salary, extra_hours, bonus_amount, total_salary))
        db.commit()
        
        cursor.close()
        db.close()
        
        return redirect(f'/admin/salary_management?month={month}&success=true')
    except mysql.connector.Error as err:
        cursor.close()
        db.close()
        return redirect(f'/admin/salary_management?month={month}&error={str(err)}')

# ----- Update Salary Status -----
@app.route('/admin/salary/<int:salary_id>/update-status', methods=['POST'])
def update_salary_status(salary_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    new_status = request.form.get('status')
    
    if new_status not in ['Draft', 'Finalized', 'Paid']:
        return jsonify({'error': 'Invalid status'}), 400
    
    db = get_db_connection()
    cursor = db.cursor()
    
    cursor.execute("UPDATE SALARY SET status=%s WHERE salary_id=%s", 
                   (new_status, salary_id))
    db.commit()
    
    cursor.close()
    db.close()
    
    return jsonify({'success': True, 'new_status': new_status})

# ----- Approve Substitutes -----
@app.route('/admin/approve_substitutes')
def approve_substitutes():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get admin data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    admin = cursor.fetchone()
    
    # Get all substitute requests that are accepted by substitute but need admin approval
    cursor.execute("""
        SELECT 
            sr.*,
            r.name as requester_name,
            r.department as requester_dept,
            s.name as substitute_name,
            s.department as substitute_dept
        FROM SUBSTITUTE_REQUEST sr
        JOIN WORKER r ON sr.requester_id = r.worker_id
        JOIN WORKER s ON sr.substitute_id = s.worker_id
        WHERE sr.status = 'Accepted' 
        AND sr.admin_approved = FALSE
        ORDER BY sr.date DESC
    """)
    pending_requests = cursor.fetchall()
    
    # Get recently approved requests
    cursor.execute("""
        SELECT 
            sr.*,
            r.name as requester_name,
            s.name as substitute_name
        FROM SUBSTITUTE_REQUEST sr
        JOIN WORKER r ON sr.requester_id = r.worker_id
        JOIN WORKER s ON sr.substitute_id = s.worker_id
        WHERE sr.admin_approved = TRUE
        ORDER BY sr.date DESC
        LIMIT 10
    """)
    approved_requests = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('admin/approve_substitutes.html',
                         admin=admin,
                         pending_requests=pending_requests,
                         approved_requests=approved_requests)

# ----- Approve/Reject Substitute Request -----
@app.route('/admin/substitute/<int:request_id>/<action>', methods=['POST'])
def handle_substitute_approval(request_id, action):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    if action not in ['approve', 'reject']:
        return redirect('/admin/approve_substitutes?error=invalid_action')
    
    db = get_db_connection()
    cursor = db.cursor()
    
    if action == 'approve':
        cursor.execute("""
            UPDATE SUBSTITUTE_REQUEST 
            SET admin_approved = TRUE 
            WHERE sub_id = %s
        """, (request_id,))
    else:  # reject
        cursor.execute("""
            UPDATE SUBSTITUTE_REQUEST 
            SET status = 'Rejected' 
            WHERE sub_id = %s
        """, (request_id,))
    
    db.commit()
    cursor.close()
    db.close()
    
    return redirect('/admin/approve_substitutes?success=true')
# Add these routes after your existing admin routes

# ----- Admin Approve Leave -----
@app.route('/admin/approve_leave')
def admin_approve_leave():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get admin data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    admin = cursor.fetchone()
    
    # Get all leave requests with worker details
    cursor.execute("""
        SELECT lr.*, 
               w.name as worker_name, 
               w.department,
               w.worker_id,
               a.name as approved_by_name
        FROM LEAVE_REQUEST lr
        JOIN WORKER w ON lr.worker_id = w.worker_id
        LEFT JOIN WORKER a ON lr.approved_by = a.worker_id
        ORDER BY lr.applied_date DESC
    """)
    leave_requests = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('admin/approve_leave.html',
                         admin=admin,
                         leave_requests=leave_requests)

# ----- Approve Leave Request -----
@app.route('/admin/leave/<int:leave_id>/approve', methods=['POST'])
def approve_leave_request(leave_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # Update leave request status
        cursor.execute("""
            UPDATE LEAVE_REQUEST 
            SET status = 'Approved', 
                approved_by = %s, 
                approval_date = CURDATE()
            WHERE leave_id = %s
        """, (session['user_id'], leave_id))
        
        db.commit()
        cursor.close()
        db.close()
        
        return redirect('/admin/approve_leave?success=approved')
    except mysql.connector.Error as err:
        cursor.close()
        db.close()
        return redirect(f'/admin/approve_leave?error={str(err)}')

# ----- Reject Leave Request -----
@app.route('/admin/leave/<int:leave_id>/reject', methods=['POST'])
def reject_leave_request(leave_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # Update leave request status
        cursor.execute("""
            UPDATE LEAVE_REQUEST 
            SET status = 'Rejected', 
                approved_by = %s, 
                approval_date = CURDATE()
            WHERE leave_id = %s
        """, (session['user_id'], leave_id))
        
        db.commit()
        cursor.close()
        db.close()
        
        return redirect('/admin/approve_leave?success=rejected')
    except mysql.connector.Error as err:
        cursor.close()
        db.close()
        return redirect(f'/admin/approve_leave?error={str(err)}')


# ============ MANAGER ROUTES ============

# ----- Manager Dashboard -----
@app.route('/manager/dashboard')
def manager_dashboard():
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get manager data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    manager = cursor.fetchone()
    
    if not manager:
        session.clear()
        return redirect('/login')
    
    # Get manager's team (workers in same department)
    cursor.execute("""
        SELECT COUNT(*) as team_count 
        FROM WORKER 
        WHERE department = %s AND role = 'worker' AND status = 'Active'
    """, (manager['department'],))
    team_stats = cursor.fetchone()
    
    # Get pending tasks in manager's department
    cursor.execute("""
        SELECT COUNT(*) as pending_tasks
        FROM TASK t
        JOIN WORKER w ON t.worker_id = w.worker_id
        WHERE w.department = %s AND t.status IN ('Pending', 'In Progress')
    """, (manager['department'],))
    task_stats = cursor.fetchone()
    
    # Get today's attendance for team
    cursor.execute("""
        SELECT COUNT(DISTINCT w.worker_id) as today_present
        FROM ATTENDANCE a
        JOIN WORKER w ON a.worker_id = w.worker_id
        WHERE w.department = %s AND a.date = CURDATE() AND a.attendance_value >= 0.5
    """, (manager['department'],))
    attendance_stats = cursor.fetchone()
    
    # Get pending leave requests
    cursor.execute("""
        SELECT COUNT(*) as pending_leaves
        FROM LEAVE_REQUEST lr
        JOIN WORKER w ON lr.worker_id = w.worker_id
        WHERE w.department = %s AND lr.status = 'Pending'
    """, (manager['department'],))
    leave_stats = cursor.fetchone()
    
    # Recent team activity (tasks)
    cursor.execute("""
        SELECT w.name, t.task_details, t.status, t.deadline
        FROM TASK t
        JOIN WORKER w ON t.worker_id = w.worker_id
        WHERE w.department = %s
        ORDER BY t.deadline ASC
        LIMIT 5
    """, (manager['department'],))
    recent_tasks = cursor.fetchall()
    
    # Today's attendance
    cursor.execute("""
        SELECT w.name, a.date, a.check_in, a.check_out
        FROM ATTENDANCE a
        JOIN WORKER w ON a.worker_id = w.worker_id
        WHERE w.department = %s AND a.date = CURDATE()
        ORDER BY a.check_in DESC
        LIMIT 5
    """, (manager['department'],))
    today_attendance = cursor.fetchall()
    
    # Recent leave requests
    cursor.execute("""
        SELECT lr.*, w.name as worker_name
        FROM LEAVE_REQUEST lr
        JOIN WORKER w ON lr.worker_id = w.worker_id
        WHERE w.department = %s
        ORDER BY lr.applied_date DESC
        LIMIT 5
    """, (manager['department'],))
    recent_leaves = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('manager/dashboard.html',
                         manager=manager,
                         team_count=team_stats['team_count'] if team_stats else 0,
                         pending_tasks=task_stats['pending_tasks'] if task_stats else 0,
                         today_present=attendance_stats['today_present'] if attendance_stats else 0,
                         pending_leaves=leave_stats['pending_leaves'] if leave_stats else 0,
                         recent_tasks=recent_tasks,
                         today_attendance=today_attendance,
                         recent_leaves=recent_leaves)

# ----- Manager Profile -----
@app.route('/manager/profile')
def manager_profile():
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    manager = cursor.fetchone()
    cursor.close()
    db.close()
    
    return render_template('manager/profile.html', manager=manager)

# ----- Update Manager Profile -----
@app.route('/manager/profile/update', methods=['POST'])
def update_manager_profile():
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    contact = request.form.get('contact')
    address = request.form.get('address')
    
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE WORKER SET contact=%s, address=%s WHERE worker_id=%s", 
                   (contact, address, session['user_id']))
    db.commit()
    cursor.close()
    db.close()
    
    return redirect('/manager/profile?success=updated')

# ----- Change Manager Password -----
@app.route('/manager/profile/change-password', methods=['POST'])
def change_manager_password():
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if new_password != confirm_password:
        return redirect('/manager/profile?error=password_mismatch')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Verify current password
    cursor.execute("SELECT password FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    manager = cursor.fetchone()
    
    if manager['password'] != current_password:
        cursor.close()
        db.close()
        return redirect('/manager/profile?error=wrong_password')
    
    # Update password
    cursor.execute("UPDATE WORKER SET password=%s WHERE worker_id=%s", 
                   (new_password, session['user_id']))
    db.commit()
    
    cursor.close()
    db.close()
    
    return redirect('/manager/profile?success=password_changed')

# ----- Team View -----
@app.route('/manager/team_view')
def team_view():
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get manager data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    manager = cursor.fetchone()
    
    # Get team members (workers in same department)
    cursor.execute("""
        SELECT w.*, 
               (SELECT COUNT(*) FROM TASK t WHERE t.worker_id = w.worker_id AND t.status != 'Completed') as pending_tasks,
               (SELECT COUNT(*) FROM ATTENDANCE a WHERE a.worker_id = w.worker_id AND a.date = CURDATE() AND a.attendance_value >= 0.5) as today_attended
        FROM WORKER w
        WHERE w.department = %s 
        AND w.role = 'worker'
        AND w.status = 'Active'
        ORDER BY w.name
    """, (manager['department'],))
    team_members = cursor.fetchall()
    
    # Get team statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total_team,
            SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) as active_members,
            SUM(CASE WHEN status = 'On Leave' THEN 1 ELSE 0 END) as on_leave,
            SUM(CASE WHEN status = 'Inactive' THEN 1 ELSE 0 END) as inactive_members
        FROM WORKER
        WHERE department = %s AND role = 'worker'
    """, (manager['department'],))
    team_stats = cursor.fetchone()
    
    # Get department task statistics
    cursor.execute("""
        SELECT 
            t.status,
            COUNT(*) as count
        FROM TASK t
        JOIN WORKER w ON t.worker_id = w.worker_id
        WHERE w.department = %s
        GROUP BY t.status
    """, (manager['department'],))
    task_stats = cursor.fetchall()
    
    # Get department attendance summary for current month
    cursor.execute("""
        SELECT 
            DATE_FORMAT(a.date, '%Y-%m-%d') as date,
            COUNT(*) as present_count
        FROM ATTENDANCE a
        JOIN WORKER w ON a.worker_id = w.worker_id
        WHERE w.department = %s 
        AND DATE_FORMAT(a.date, '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m')
        AND a.attendance_value >= 0.5
        GROUP BY a.date
        ORDER BY a.date DESC
        LIMIT 10
    """, (manager['department'],))
    attendance_data = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('manager/team_view.html',
                         manager=manager,
                         team_members=team_members,
                         team_stats=team_stats,
                         task_stats=task_stats,
                         attendance_data=attendance_data)

# ----- Assign Tasks -----
@app.route('/manager/assign_tasks')
def assign_tasks():
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get manager data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    manager = cursor.fetchone()
    
    # Get team members for task assignment
    cursor.execute("""
        SELECT worker_id, name, department
        FROM WORKER 
        WHERE department = %s 
        AND role = 'worker'
        AND status = 'Active'
        ORDER BY name
    """, (manager['department'],))
    team_members = cursor.fetchall()
    
    # Get existing tasks for manager's team
    cursor.execute("""
        SELECT t.*, w.name as worker_name
        FROM TASK t
        JOIN WORKER w ON t.worker_id = w.worker_id
        WHERE w.department = %s
        ORDER BY t.deadline ASC
    """, (manager['department'],))
    existing_tasks = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('manager/assign_tasks.html',
                         manager=manager,
                         team_members=team_members,
                         existing_tasks=existing_tasks)

# ----- Submit New Task -----
@app.route('/manager/task/assign', methods=['POST'])
def assign_new_task():
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    worker_id = request.form.get('worker_id')
    task_details = request.form.get('task_details')
    deadline = request.form.get('deadline')
    
    if not all([worker_id, task_details, deadline]):
        return redirect('/manager/assign_tasks?error=missing_fields')
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # Verify worker is in manager's department
        cursor.execute("SELECT department FROM WORKER WHERE worker_id=%s", (worker_id,))
        worker = cursor.fetchone()
        
        cursor.execute("SELECT department FROM WORKER WHERE worker_id=%s", (session['user_id'],))
        manager = cursor.fetchone()
        
        if not worker or worker[0] != manager[0]:
            cursor.close()
            db.close()
            return redirect('/manager/assign_tasks?error=unauthorized')
        
        sql = """
        INSERT INTO TASK (worker_id, task_details, deadline, status, assigned_date)
        VALUES (%s, %s, %s, 'Pending', CURDATE())
        """
        cursor.execute(sql, (worker_id, task_details, deadline))
        db.commit()
        
        cursor.close()
        db.close()
        
        return redirect('/manager/assign_tasks?success=true')
    except mysql.connector.Error as err:
        cursor.close()
        db.close()
        return redirect(f'/manager/assign_tasks?error={str(err)}')

# ----- Update Task Status -----
@app.route('/manager/task/<int:task_id>/update-status', methods=['POST'])
def update_task_status_manager(task_id):
    if 'user_id' not in session or session['role'] != 'manager':
        return jsonify({'error': 'Unauthorized'}), 401
    
    status = request.form.get('status')
    
    if status not in ['Pending', 'In Progress', 'Completed', 'Delayed']:
        return jsonify({'error': 'Invalid status'}), 400
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # Verify task belongs to manager's department
        cursor.execute("""
            SELECT w.department 
            FROM TASK t
            JOIN WORKER w ON t.worker_id = w.worker_id
            WHERE t.task_id = %s
        """, (task_id,))
        task_dept = cursor.fetchone()
        
        cursor.execute("SELECT department FROM WORKER WHERE worker_id=%s", (session['user_id'],))
        manager_dept = cursor.fetchone()
        
        if task_dept and manager_dept and task_dept[0] == manager_dept[0]:
            cursor.execute("UPDATE TASK SET status=%s WHERE task_id=%s", (status, task_id))
            db.commit()
            success = True
        else:
            success = False
    
    except mysql.connector.Error:
        success = False
    
    cursor.close()
    db.close()
    
    if success:
        return jsonify({'success': True, 'new_status': status})
    else:
        return jsonify({'error': 'Unauthorized or task not found'}), 403

# ----- Delete Task -----
@app.route('/manager/task/<int:task_id>/delete', methods=['POST'])
def delete_task_manager(task_id):
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # Verify task belongs to manager's department
        cursor.execute("""
            SELECT w.department 
            FROM TASK t
            JOIN WORKER w ON t.worker_id = w.worker_id
            WHERE t.task_id = %s
        """, (task_id,))
        task_dept = cursor.fetchone()
        
        cursor.execute("SELECT department FROM WORKER WHERE worker_id=%s", (session['user_id'],))
        manager_dept = cursor.fetchone()
        
        if task_dept and manager_dept and task_dept[0] == manager_dept[0]:
            cursor.execute("DELETE FROM TASK WHERE task_id=%s", (task_id,))
            db.commit()
            success = True
        else:
            success = False
    
    except mysql.connector.Error:
        success = False
    
    cursor.close()
    db.close()
    
    if success:
        return redirect('/manager/assign_tasks?success=deleted')
    else:
        return redirect('/manager/assign_tasks?error=unauthorized')



# ----- Give Feedback -----
@app.route('/manager/feedback')
def manager_feedback():
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get manager data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    manager = cursor.fetchone()
    
    # Get team members for feedback
    cursor.execute("""
        SELECT w.*
        FROM WORKER w
        WHERE w.department = %s 
        AND w.role = 'worker'
        AND w.status = 'Active'
        ORDER BY w.name
    """, (manager['department'],))
    team_members = cursor.fetchall()
    
    # Get existing performance feedback
    cursor.execute("""
        SELECT p.*, w.name as worker_name
        FROM PERFORMANCE p
        JOIN WORKER w ON p.worker_id = w.worker_id
        WHERE w.department = %s
        ORDER BY p.month DESC
    """, (manager['department'],))
    existing_feedback = cursor.fetchall()
    
    # Get current month and year for default selection
    current_month = datetime.now().strftime('%Y-%m')
    
    cursor.close()
    db.close()
    
    return render_template('manager/feedback.html',
                         manager=manager,
                         team_members=team_members,
                         existing_feedback=existing_feedback,
                         current_month=current_month)

# ----- Submit Feedback -----
@app.route('/manager/feedback/submit', methods=['POST'])
def submit_feedback():
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    worker_id = request.form.get('worker_id')
    month = request.form.get('month')
    feedback = request.form.get('feedback')
    
    if not all([worker_id, month, feedback]):
        return redirect('/manager/feedback?error=missing_fields')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    try:
        # Verify worker is in manager's department
        cursor.execute("SELECT department FROM WORKER WHERE worker_id=%s", (worker_id,))
        worker = cursor.fetchone()
        
        cursor.execute("SELECT department FROM WORKER WHERE worker_id=%s", (session['user_id'],))
        manager = cursor.fetchone()
        
        if not worker or worker['department'] != manager['department']:
            cursor.close()
            db.close()
            return redirect('/manager/feedback?error=unauthorized')
        
        # Check if performance record exists for this month
        cursor.execute("""
            SELECT * FROM PERFORMANCE 
            WHERE worker_id = %s AND month = %s
        """, (worker_id, month))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing record
            cursor.execute("""
                UPDATE PERFORMANCE 
                SET manager_feedback = %s 
                WHERE worker_id = %s AND month = %s
            """, (feedback, worker_id, month))
        else:
            # Create new performance record
            # Get attendance data for the month
            cursor.execute("""
                SELECT 
                    AVG(attendance_value) * 100 as attendance_percentage,
                    SUM(working_hours) as total_hours
                FROM ATTENDANCE
                WHERE worker_id = %s 
                AND DATE_FORMAT(date, '%Y-%m') = %s
            """, (worker_id, month))
            stats = cursor.fetchone()
            
            sql = """
            INSERT INTO PERFORMANCE (worker_id, month, attendance_percentage, total_hours, manager_feedback)
            VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (worker_id, month, 
                               stats['attendance_percentage'] if stats and stats['attendance_percentage'] else 0,
                               stats['total_hours'] if stats and stats['total_hours'] else 0,
                               feedback))
        
        db.commit()
        cursor.close()
        db.close()
        
        return redirect('/manager/feedback?success=true')
    except mysql.connector.Error as err:
        cursor.close()
        db.close()
        return redirect(f'/manager/feedback?error={str(err)}')

# ----- View Worker Details (Manager) -----
@app.route('/manager/worker/<int:worker_id>')
def manager_view_worker(worker_id):
    if 'user_id' not in session or session['role'] != 'manager':
        return redirect('/login')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)
    
    # Get manager data
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (session['user_id'],))
    manager = cursor.fetchone()
    
    # Get worker details
    cursor.execute("SELECT * FROM WORKER WHERE worker_id=%s", (worker_id,))
    worker = cursor.fetchone()
    
    # Verify worker is in manager's department
    if not worker or worker['department'] != manager['department']:
        cursor.close()
        db.close()
        return redirect('/manager/team_view?error=unauthorized')
    
    # Get worker attendance (last 30 days)
    cursor.execute("""
        SELECT * FROM ATTENDANCE 
        WHERE worker_id = %s 
        ORDER BY date DESC 
        LIMIT 30
    """, (worker_id,))
    attendance = cursor.fetchall()
    
    # Get worker tasks
    cursor.execute("""
        SELECT * FROM TASK 
        WHERE worker_id = %s 
        ORDER BY deadline
    """, (worker_id,))
    tasks = cursor.fetchall()
    
    # Get worker performance
    cursor.execute("""
        SELECT * FROM PERFORMANCE 
        WHERE worker_id = %s 
        ORDER BY month DESC
    """, (worker_id,))
    performances = cursor.fetchall()
    
    # Get worker leave requests
    cursor.execute("""
        SELECT * FROM LEAVE_REQUEST 
        WHERE worker_id = %s 
        ORDER BY start_date DESC
        LIMIT 10
    """, (worker_id,))
    leave_requests = cursor.fetchall()
    
    # ADD THIS SECTION: Get team statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total_team,
            SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) as active_members,
            SUM(CASE WHEN status = 'On Leave' THEN 1 ELSE 0 END) as on_leave,
            SUM(CASE WHEN status = 'Inactive' THEN 1 ELSE 0 END) as inactive_members
        FROM WORKER
        WHERE department = %s AND role = 'worker'
    """, (manager['department'],))
    team_stats = cursor.fetchone()
    
    cursor.close()
    db.close()
    
    return render_template('manager/worker_details.html',
                         manager=manager,
                         worker=worker,
                         attendance=attendance,
                         tasks=tasks,
                         performances=performances,
                         leave_requests=leave_requests,
                         team_stats=team_stats)  
# ============ RUN APP ============
if __name__ == '__main__':
    print("\n" + "="*60)
    print(" SMART LABOUR MANAGEMENT SYSTEM")
    print("="*60)
    
    print(f"\n📁 Templates folder: {TEMPLATES_DIR}")
    print(f"📁 Static folder: {STATIC_DIR}")
    
    print("\n🎨 Custom Jinja2 Filters Loaded:")
    print("   • currency: Format as ৳1,234.56")
    print("   • pad_id: Format as WKR-0001")
    print("   • percentage: Format as 95.5%")
    print("   • hours: Format as 8.5 hrs")
    print("   • date_only: Extract date only")
    
    print("\n🚀 AVAILABLE ROUTES:")
    print("-"*40)
    
    print("\n🔐 AUTHENTICATION:")
    print("   • /login           - Login page")
    print("   • /signup          - Sign up page")
    print("   • /logout          - Logout")
    
    print("\n👷 WORKER FEATURES:")
    print("   • /worker/dashboard      - Worker dashboard")
    print("   • /worker/profile        - Worker profile")
    print("   • /worker/tasks          - Worker tasks")
    print("   • /worker/attendance     - Attendance tracking")
    print("   • /worker/substitute     - Substitute requests")
    print("   • /worker/leave          - Leave management")
    print("   • /worker/salary         - Salary view")
    print("   • /worker/performance    - Performance tracking")
    
    print("\n👨‍💼 MANAGER FEATURES:")
    print("   • /manager/dashboard     - Manager dashboard")
    print("   • /manager/profile       - Manager profile")
    print("   • /manager/team_view     - Team management")
    print("   • /manager/assign_tasks  - Assign tasks")
    print("   • /manager/approve_leave - Approve leave requests")
    print("   • /manager/feedback      - Give feedback")
    
    print("\n👑 ADMIN FEATURES:")
    print("   • /admin/dashboard       - Admin dashboard")
    print("   • /admin/profile         - Admin profile")
    print("   • /admin/all_workers     - All workers view")
    print("   • /admin/attendance_reports - Attendance reports")
    print("   • /admin/salary_management   - Salary management")
    print("   • /admin/approve_substitutes - Approve substitutes")
    print("   • /admin/worker/<id>     - Worker details (admin)")
    print("   • /manager/worker/<id>   - Worker details (manager)")
    
    print("\n🛠️  API ENDPOINTS:")
    print("   • /worker/task/<id>/update-status   - Update task status")
    print("   • /worker/task/<id>                 - Get task details")
    print("   • /admin/worker/<id>/update-status  - Update worker status")
    print("   • /admin/salary/<id>/update-status  - Update salary status")
    print("   • /manager/task/<id>/update-status  - Update task (manager)")
    
    print("\n" + "="*60)
    print("🌐 Server starting on http://localhost:5000")
    print("="*60 + "\n")
    
    app.run(debug=True, port=5000)