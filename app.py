import cv2
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import pymysql
from ultralytics import YOLO
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = '123456'


db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'edu_system',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor   #以字典的形式存储数据库查询返回值
}


def get_db():
    return pymysql.connect(**db_config)         #封装数据库连接函数，每次调用此函数都返回一次新的连接


def login_required(f):                      #f为要保护的视图
    @wraps(f)                   #登陆装饰器，保护需要登录才能访问的页面，如果页面上有此类数据，那么就重新定向到登陆页面，保证启动程序首页为登录
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:                #如果会话中有user_id，就重定向到login页面
            return redirect(url_for('login'))
        return f(*args, **kwargs)              #判断结束，如果已经登录就返回原来的视图，也就是正常的页面。

    return decorated_function              #返回包装后的函数


def admin_required(f):
    @wraps(f)                                    #同样的道理，保护需要管理员身份才能访问的数据
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('需要管理员权限')
            return redirect(url_for('user_dashboard'))
        return f(*args, **kwargs)

    return decorated_function


def init_db():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 用户表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(200) NOT NULL,
                    role VARCHAR(10) DEFAULT 'user',
                    name VARCHAR(50),
                    student_id VARCHAR(20) UNIQUE,
                    department VARCHAR(100),                
                    phone VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')            #加入了院系（department） 创建时间（create_at），AUTO_INCREMENT为自动增长

            # 成绩表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS grades (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id INT NOT NULL,
                    course_name VARCHAR(100) NOT NULL,
                    score FLOAT,
                    semester VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (student_id) REFERENCES users(id)
                )
            ''')

            # 课程表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schedules (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id INT NOT NULL,
                    course_name VARCHAR(100) NOT NULL,
                    class_time VARCHAR(100),
                    location VARCHAR(100),
                    teacher VARCHAR(50),
                    semester VARCHAR(20),
                    FOREIGN KEY (student_id) REFERENCES users(id)
                )
            ''')

            # 公告表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS announcements (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    content TEXT NOT NULL,
                    author_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (author_id) REFERENCES users(id)
                )
            ''')

            # 申请表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS requests (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    request_type VARCHAR(50),
                    content TEXT NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    reply TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # 可选课程表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS courses (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    course_code VARCHAR(20) UNIQUE NOT NULL,
                    course_name VARCHAR(200) NOT NULL,
                    department VARCHAR(100),
                    credits INT DEFAULT 3,
                    max_students INT DEFAULT 50,
                    current_students INT DEFAULT 0,
                    teacher VARCHAR(100),
                    schedule VARCHAR(200)
                )
            ''')

            # 选课关系表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS course_selections (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id INT NOT NULL,
                    course_id INT NOT NULL,
                    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (student_id) REFERENCES users(id),
                    FOREIGN KEY (course_id) REFERENCES courses(id),
                    UNIQUE KEY unique_selection (student_id, course_id)
                )
            ''')
                                                     #添加唯一约束，确保同一个学生同一门课只能选择一次
            # 检查管理员是否存在
            cursor.execute("SELECT * FROM users WHERE username = 'admin'")
            admin = cursor.fetchone()
            if not admin:
                hashed_pwd = generate_password_hash('admin123')
                cursor.execute("""
                    INSERT INTO users (username, password, role, name) 
                    VALUES (%s, %s, %s, %s)
                """, ('admin', hashed_pwd, 'admin', '系统管理员'))

            conn.commit()
    except Exception as e:
        print(f"数据库初始化失败: {e}")
    finally:
        conn.close()


init_db()

@app.route('/')
def index():
    session.clear()           #session是Flask内置对象，导入即可，作用：防止在登陆后浏览不同页面需要重新登陆
    return redirect(url_for('login'))



#session 中的内容可以包含= {
#    'user_id': 123,
#    'username': '张三',
#    'role': 'student',
#}

@app.route('/login', methods=['GET', 'POST'])        #get请求就是获取信息，post请求就是发送信息
def login():
    if request.method == 'GET':
        if 'user_id' in session:
            if session['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        return render_template('login.html')

    username = request.form['username']           #从HTML中获取表单信息
    password = request.form['password']

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()         #从数据库查询结果中获取一行信息

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                session['name'] = user['name']

                if user['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('user_dashboard'))
            else:
                return "用户名或密码错误 <a href='/login'>返回登录</a>"
    finally:
        conn.close()


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/user/dashboard')
@login_required             #装饰器，保护这个页面，意味着此函数操作需要登录
def user_dashboard():
    if session['role'] != 'user':
        return redirect(url_for('admin_dashboard'))

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 获取用户信息
            cursor.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
            user = cursor.fetchone()

            # 获取成绩
            cursor.execute("SELECT * FROM grades WHERE student_id = %s", (session['user_id'],))
            grades = cursor.fetchall()     #从查询结果中获取所有行的信息

            # 获取课程表
            cursor.execute("SELECT * FROM schedules WHERE student_id = %s", (session['user_id'],))
            schedules = cursor.fetchall()

            # 获取公告
            cursor.execute("""
                SELECT a.*, u.name as author_name FROM announcements a 
                JOIN users u ON a.author_id = u.id 
                ORDER BY a.created_at DESC LIMIT 5
            """)
            announcements = cursor.fetchall()

            # 获取申请
            cursor.execute("SELECT * FROM requests WHERE user_id = %s ORDER BY created_at DESC", (session['user_id'],))
            requests = cursor.fetchall()

            # 获取可选课程
            cursor.execute("SELECT * FROM courses")
            courses = cursor.fetchall()

            # 获取已选课程
            cursor.execute("""
                SELECT c.* FROM courses c 
                JOIN course_selections cs ON c.id = cs.course_id 
                WHERE cs.student_id = %s
            """, (session['user_id'],))
            selected_courses = cursor.fetchall()

    finally:
        conn.close()

    return render_template('user/dashboard.html',         #把这些参数传递给页面模板，在模板中可以直接使用
                           user=user,
                           grades=grades,
                           schedules=schedules,
                           announcements=announcements,
                           requests=requests,
                           courses=courses,
                           selected_courses=selected_courses)


@app.route('/user/grades')
@login_required
def user_grades():
    if session['role'] != 'user':
        return redirect(url_for('admin_dashboard'))

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM grades WHERE student_id = %s ORDER BY semester DESC", (session['user_id'],))  #ORDER BY semester DESC查询结果按学期字段降序（DESC）排序
            grades = cursor.fetchall()
    finally:
        conn.close()

    return render_template('user/grades.html', grades=grades)



@app.route('/user/schedule')
@login_required
def user_schedule():
    if session['role'] != 'user':
        return redirect(url_for('admin_dashboard'))

    conn = get_db()
    try:                                      #cursor=conn.cursor()创建游标,通过游标进行操作
        with conn.cursor() as cursor:        #查询courses表中的所有列，c是course的简称，Join连接其他两个表，连接条件是c.id = cs.course_id
            cursor.execute("""
                SELECT c.* FROM courses c        
                JOIN course_selections cs ON c.id = cs.course_id 
                WHERE cs.student_id = %s
            """, (session['user_id'],))
            selected_courses = cursor.fetchall()

            cursor.execute("SELECT * FROM schedules WHERE student_id = %s ORDER BY class_time", (session['user_id'],)) #按存储顺序排序
            schedules = cursor.fetchall()
    finally:
        conn.close()

    return render_template('user/schedule.html',
                           selected_courses=selected_courses,
                           schedules=schedules)


@app.route('/user/courses')
@login_required
def user_courses():
    if session['role'] != 'user':
        return redirect(url_for('admin_dashboard'))

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM courses")
            courses = cursor.fetchall()
            cursor.execute("""
                SELECT c.* FROM courses c 
                JOIN course_selections cs ON c.id = cs.course_id 
                WHERE cs.student_id = %s
            """, (session['user_id'],))
            selected_courses = cursor.fetchall()

            selected_ids = [course['id'] for course in selected_courses]   #使用推导式，从字典列表中提取每个id字段创建一个新的列表
    finally:
        conn.close()

    return render_template('user/courses.html',
                           courses=courses,
                           selected_courses=selected_courses,
                           selected_ids=selected_ids)


@app.route('/user/select_course/<int:course_id>')       #<int:course_id>表示course_id会被转化为int传给视图
@login_required
def select_course(course_id):
    if session['role'] != 'user':
        return redirect(url_for('admin_dashboard'))

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM course_selections WHERE student_id = %s AND course_id = %s",
                           (session['user_id'], course_id))
            if cursor.fetchone():
                return "已选过此课程 <a href='/user/courses'>返回</a>"

            cursor.execute("INSERT INTO course_selections (student_id, course_id) VALUES (%s, %s)",
                           (session['user_id'], course_id))

            cursor.execute("UPDATE courses SET current_students = current_students + 1 WHERE id = %s", (course_id,))

            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('user_courses'))



@app.route('/user/withdraw_course/<int:course_id>')
@login_required
def withdraw_course(course_id):
    if session['role'] != 'user':
        return redirect(url_for('admin_dashboard'))

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM course_selections WHERE student_id = %s AND course_id = %s",
                           (session['user_id'], course_id))

            cursor.execute("UPDATE courses SET current_students = current_students - 1 WHERE id = %s", (course_id,))

            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('user_courses'))



######################################################################
@app.route('/user/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if session['role'] != 'user':
        return redirect(url_for('admin_dashboard'))

    if request.method == 'GET':
        return render_template('user/change_password.html')

    elif request.method == 'POST':
        old_password = request.form.get('old_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if new_password != confirm_password:
            return jsonify({'success': False, 'message': '新密码不一致'})

        if len(new_password) < 6:
            return jsonify({'success': False, 'message': '密码长度至少6位'})

        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT password FROM users WHERE id = %s", (session['user_id'],))
                user = cursor.fetchone()

                if not check_password_hash(user['password'], old_password):
                    return jsonify({'success': False, 'message': '当前密码错误'})
        finally:
            conn.close()

        face_verified = perform_face_verification()

        if not face_verified:
            return jsonify({'success': False, 'message': '人脸验证失败，请重试'})

        conn = get_db()
        try:
            with conn.cursor() as cursor:
                hashed_pwd = generate_password_hash(new_password)
                cursor.execute("UPDATE users SET password = %s WHERE id = %s",
                               (hashed_pwd, session['user_id']))
                conn.commit()             #提交事务，使得之前对数据库的更改有效
        finally:
            conn.close()

        return jsonify({'success': True, 'message': '密码修改成功'})


def perform_face_verification():
    try:
        model = YOLO("best.pt", task="detect") #加载YOLO模型，指定检测任务
        cap = cv2.VideoCapture(0)#打开摄像头
        if not cap.isOpened():#检查是否正确打开摄像头
            return False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)#设置检测框宽度
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        YOUR_CLASS_ID = 0   #设置检测目标标签为0
        CONFIDENCE_THRESHOLD = 0.9  #设置置信度为90%
        max_attempts = 30    #设置处理最大帧数
        attempt = 0   #记录处理的帧数

        while attempt < max_attempts:
            ret, frame = cap.read()  #ret为布尔值，代表是否正确读取帧数据
            if not ret:               #frame为图像数据
                attempt += 1
                continue

            results = model(frame, verbose=False) #使用YOLO模型对当前帧进行检测，verbose=False为不显示处理进度

            if len(results[0].boxes) > 0: # 检查是否有检测到任何目标
                boxes = results[0].boxes  #获取所有检测框的信息
                for box in boxes:  #遍历每个检测框，看是否有标签为0的
                    class_id = int(box.cls[0])   #获取正在检测的检测框标签
                    confidence = float(box.conf[0])  #获取置信度

                    if class_id == YOUR_CLASS_ID and confidence >= CONFIDENCE_THRESHOLD:
                        print(f"人脸验证成功！置信度: {confidence:.2%}")

                        x1, y1, x2, y2 = map(int, box.xyxy[0])  #提取检测框的坐标，左上角和右下角
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)  # 在图像上绘制绿色矩形框标记人脸
                        cv2.putText(frame, f"Face: {confidence:.2%}",   #在矩形框上方添加置信度文本
                                    (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.5, (0, 255, 0), 2)

                        cv2.imshow("Face Verification", frame)  #显示带有标记的图像
                        cv2.waitKey(500)  #等待500毫秒，让用户看到验证成功的画面

                        cap.release()  #释放摄像头资源和关闭所有OpenCV窗口
                        cv2.destroyAllWindows()

                        return True

            cv2.imshow("Face Verification", frame)  #如果没有检测到合格的人脸，显示当前帧

            attempt += 1

        cap.release()
        cv2.destroyAllWindows()
        return False

    except Exception as e:
        print(f"人脸验证过程中出错: {e}")
        return False


@app.route('/user/create_request', methods=['POST'])
@login_required
def create_request():
    if session['role'] != 'user':
        return redirect(url_for('admin_dashboard'))

    request_type = request.form['request_type']
    content = request.form['content']

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO requests (user_id, request_type, content, status) 
                VALUES (%s, %s, %s, 'pending')
            """, (session['user_id'], request_type, content))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('user_dashboard'))


@app.route('/admin/dashboard')
@login_required              #装饰器，需要登陆、需要管理员权限
@admin_required
def admin_dashboard():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'user'")
            user_count = cursor.fetchone()['count']   #获取从数据库中查询的数据的数量

            cursor.execute("SELECT COUNT(*) as count FROM announcements")
            announcement_count = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM requests WHERE status = 'pending'")
            pending_requests = cursor.fetchone()['count']
    finally:
        conn.close()

    return render_template('admin/dashboard.html',
                           user_count=user_count,
                           announcement_count=announcement_count,
                           pending_requests=pending_requests)


@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users ORDER BY id DESC")
            users = cursor.fetchall()
    finally:
        conn.close()

    return render_template('admin/users.html', users=users)


@app.route('/admin/create_user', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_create_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        student_id = request.form['student_id']
        department = request.form['department']
        phone = request.form['phone']
        role = request.form['role']

        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                if cursor.fetchone():
                    return "用户名已存在 <a href='/admin/create_user'>返回</a>"

                if student_id:
                    cursor.execute("SELECT * FROM users WHERE student_id = %s", (student_id,))
                    if cursor.fetchone():
                        return "学号已存在 <a href='/admin/create_user'>返回</a>"

                hashed_pwd = generate_password_hash(password)
                cursor.execute("""
                    INSERT INTO users (username, password, name, student_id, department, phone, role) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (username, hashed_pwd, name, student_id, department, phone, role))
                conn.commit()
        finally:
            conn.close()

        return redirect(url_for('admin_users'))

    return render_template('admin/create_user.html')


@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user(user_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()

            if not user:
                return "用户不存在"

            if request.method == 'POST':
                username = request.form['username']
                name = request.form['name']
                student_id = request.form['student_id']
                department = request.form['department']
                phone = request.form['phone']
                role = request.form['role']
                password = request.form['password']

                cursor.execute("SELECT * FROM users WHERE username = %s AND id != %s", (username, user_id))
                if cursor.fetchone():
                    return "用户名已被使用 <a href='/admin/edit_user/{}'>返回</a>".format(user_id)

                if student_id:
                    cursor.execute("SELECT * FROM users WHERE student_id = %s AND id != %s", (student_id, user_id))
                    if cursor.fetchone():
                        return "学号已被使用 <a href='/admin/edit_user/{}'>返回</a>".format(user_id)

                if password:
                    hashed_pwd = generate_password_hash(password)
                    cursor.execute("""
                        UPDATE users SET username=%s, password=%s, name=%s, student_id=%s, 
                        department=%s, phone=%s, role=%s WHERE id=%s
                    """, (username, hashed_pwd, name, student_id, department, phone, role, user_id))
                else:
                    cursor.execute("""
                        UPDATE users SET username=%s, name=%s, student_id=%s, 
                        department=%s, phone=%s, role=%s WHERE id=%s
                    """, (username, name, student_id, department, phone, role, user_id))

                conn.commit()
                return redirect(url_for('admin_users'))
    finally:
        conn.close()

    return render_template('admin/edit_user.html', user=user)


@app.route('/admin/delete_user/<int:user_id>')
@login_required
@admin_required
def admin_delete_user(user_id):
    if user_id == session['user_id']:
        return "不能删除自己 <a href='/admin/users'>返回</a>"

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_users'))


@app.route('/admin/announcements')
@login_required
@admin_required
def admin_announcements():
    conn = get_db()
    try:
        with conn.cursor() as cursor:   #查询公告表中的所有内容和user表中的name字段，表命名为a，连接user表和公告表，条件为a.author_id = u.id
            cursor.execute("""
                SELECT a.*, u.name as author_name FROM announcements a 
                JOIN users u ON a.author_id = u.id 
                ORDER BY a.created_at DESC
            """)
            announcements = cursor.fetchall()
    finally:
        conn.close()

    return render_template('admin/announcements.html', announcements=announcements)


@app.route('/admin/create_announcement', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_create_announcement():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO announcements (title, content, author_id) 
                    VALUES (%s, %s, %s)
                """, (title, content, session['user_id']))
                conn.commit()
        finally:
            conn.close()

        return redirect(url_for('admin_announcements'))

    return render_template('admin/create_announcement.html')


@app.route('/admin/edit_announcement/<int:announcement_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_announcement(announcement_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM announcements WHERE id = %s", (announcement_id,))
            announcement = cursor.fetchone()

            if not announcement:
                return "公告不存在"

            if request.method == 'POST':
                title = request.form['title']
                content = request.form['content']

                cursor.execute("""
                    UPDATE announcements SET title=%s, content=%s WHERE id=%s
                """, (title, content, announcement_id))
                conn.commit()
                return redirect(url_for('admin_announcements'))
    finally:
        conn.close()

    return render_template('admin/edit_announcement.html', announcement=announcement)


@app.route('/admin/delete_announcement/<int:announcement_id>')
@login_required
@admin_required
def admin_delete_announcement(announcement_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM announcements WHERE id = %s", (announcement_id,))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_announcements'))


@app.route('/admin/requests')
@login_required
@admin_required
def admin_requests():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.*, u.name as user_name, u.student_id FROM requests r 
                JOIN users u ON r.user_id = u.id 
                ORDER BY r.created_at DESC
            """)
            requests = cursor.fetchall()
    finally:
        conn.close()

    return render_template('admin/requests.html', requests=requests)


@app.route('/admin/reply_request/<int:request_id>', methods=['POST'])
@login_required
@admin_required
def admin_reply_request(request_id):
    reply = request.form['reply']         #回复内容
    status = request.form['status']         #处理状态

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE requests SET reply=%s, status=%s WHERE id=%s
            """, (reply, status, request_id))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_requests'))


@app.route('/admin/manage_grades')
@login_required
@admin_required
def admin_manage_grades():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT g.*, u.name as student_name, u.student_id FROM grades g 
                JOIN users u ON g.student_id = u.id 
                ORDER BY g.semester DESC, g.course_name
            """)
            grades = cursor.fetchall()

            cursor.execute("SELECT id, name, student_id FROM users WHERE role = 'user'")
            students = cursor.fetchall()
    finally:
        conn.close()

    return render_template('admin/manage_grades.html', grades=grades, students=students)


@app.route('/admin/add_grade', methods=['POST'])
@login_required
@admin_required
def admin_add_grade():
    student_id = request.form['student_id']
    course_name = request.form['course_name']
    score = request.form['score']
    semester = request.form['semester']

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO grades (student_id, course_name, score, semester) 
                VALUES (%s, %s, %s, %s)
            """, (student_id, course_name, score, semester))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_manage_grades'))


@app.route('/admin/edit_grade/<int:grade_id>', methods=['POST'])
@login_required
@admin_required
def admin_edit_grade(grade_id):
    score = request.form['score']

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE grades SET score=%s WHERE id=%s", (score, grade_id))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_manage_grades'))


@app.route('/admin/delete_grade/<int:grade_id>')
@login_required
@admin_required
def admin_delete_grade(grade_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM grades WHERE id = %s", (grade_id,))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_manage_grades'))


@app.route('/admin/manage_schedules')
@login_required
@admin_required
def admin_manage_schedules():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT s.*, u.name as student_name, u.student_id FROM schedules s 
                JOIN users u ON s.student_id = u.id 
                ORDER BY s.class_time
            """)
            schedules = cursor.fetchall()

            cursor.execute("SELECT id, name, student_id FROM users WHERE role = 'user'")
            students = cursor.fetchall()
    finally:
        conn.close()

    return render_template('admin/manage_schedules.html', schedules=schedules, students=students)


@app.route('/admin/add_schedule', methods=['POST'])
@login_required
@admin_required
def admin_add_schedule():
    student_id = request.form['student_id']
    course_name = request.form['course_name']
    class_time = request.form['class_time']
    location = request.form['location']
    teacher = request.form['teacher']
    semester = request.form['semester']

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO schedules (student_id, course_name, class_time, location, teacher, semester) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (student_id, course_name, class_time, location, teacher, semester))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_manage_schedules'))


@app.route('/admin/delete_schedule/<int:schedule_id>')
@login_required
@admin_required
def admin_delete_schedule(schedule_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM schedules WHERE id = %s", (schedule_id,))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_manage_schedules'))


@app.route('/admin/manage_courses')
@login_required
@admin_required
def admin_manage_courses():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM courses ORDER BY course_code")
            courses = cursor.fetchall()
    finally:
        conn.close()

    return render_template('admin/manage_courses.html', courses=courses)


@app.route('/admin/add_course', methods=['POST'])
@login_required
@admin_required
def admin_add_course():
    course_code = request.form['course_code']
    course_name = request.form['course_name']
    department = request.form['department']
    credits = request.form['credits']
    max_students = request.form['max_students']
    teacher = request.form['teacher']
    schedule = request.form['schedule']

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO courses (course_code, course_name, department, credits, max_students, teacher, schedule) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (course_code, course_name, department, credits, max_students, teacher, schedule))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_manage_courses'))


@app.route('/admin/edit_course/<int:course_id>', methods=['POST'])
@login_required
@admin_required
def admin_edit_course(course_id):
    course_code = request.form['course_code']
    course_name = request.form['course_name']
    department = request.form['department']
    credits = request.form['credits']
    max_students = request.form['max_students']
    teacher = request.form['teacher']
    schedule = request.form['schedule']

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE courses SET course_code=%s, course_name=%s, department=%s, 
                credits=%s, max_students=%s, teacher=%s, schedule=%s WHERE id=%s
            """, (course_code, course_name, department, credits, max_students, teacher, schedule, course_id))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_manage_courses'))


@app.route('/admin/delete_course/<int:course_id>')
@login_required
@admin_required
def admin_delete_course(course_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM course_selections WHERE course_id = %s", (course_id,))
            cursor.execute("DELETE FROM courses WHERE id = %s", (course_id,))
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_manage_courses'))


@app.route('/admin/get_student_courses/<int:student_id>')
@login_required
@admin_required
def admin_get_student_courses(student_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT c.* FROM courses c 
                JOIN course_selections cs ON c.id = cs.course_id 
                WHERE cs.student_id = %s
            """, (student_id,))
            courses = cursor.fetchall()

            cursor.execute("SELECT * FROM schedules WHERE student_id = %s", (student_id,))
            schedules = cursor.fetchall()
    finally:
        conn.close()

    return jsonify({
        'courses': courses,
        'schedules': schedules
    })

@app.route('/admin/generate_schedule_from_selections/<int:student_id>')
@login_required
@admin_required
def generate_schedule_from_selections(student_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT c.* FROM courses c 
                JOIN course_selections cs ON c.id = cs.course_id 
                WHERE cs.student_id = %s
            """, (student_id,))
            courses = cursor.fetchall()

            for course in courses:
                cursor.execute("SELECT * FROM schedules WHERE student_id = %s AND course_name = %s",
                               (student_id, course['course_name']))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO schedules (student_id, course_name, class_time, location, teacher, semester) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (student_id, course['course_name'],
                          course['schedule'] or '待安排',
                          '待安排',
                          course['teacher'],
                          '2023-2024-2'))

            conn.commit()
    finally:
        conn.close()

    return redirect(url_for('admin_manage_schedules'))

if __name__ == '__main__':
    app.run()