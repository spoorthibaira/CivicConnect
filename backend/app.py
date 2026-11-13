
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from database import create_tables, get_db_connection
from auth import register_user, login_user
from dotenv import load_dotenv
import os
import uuid
import requests

load_dotenv()

app = Flask(
    __name__,
    template_folder="../frontend",
    static_folder="../frontend",
    static_url_path="/static"
)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "civicconnect-development-key"
)

# Create Supabase tables
create_tables()


# Home page
@app.route("/")
def home():
    return render_template("index.html")


# Citizen registration
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        if register_user(name, email, password):
            return redirect(url_for("login"))

        return "Registration failed. Email may already exist."

    return render_template("register.html")


# Citizen login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = login_user(email, password)

        if user:
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["role"] = user["role"]

            return redirect(url_for("dashboard"))

        return "Invalid email or password."

    return render_template("login.html")


# Citizen dashboard
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("dashboard.html")


# Report complaint and upload image to Supabase Storage
@app.route("/report", methods=["GET", "POST"])
def report():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        category = request.form["category"]
        location = request.form["location"]

        image = request.files.get("image")
        image_url = None

        if image and image.filename:
            filename = secure_filename(image.filename)

            if not filename:
                return "Invalid image filename."

            filename = f"{uuid.uuid4()}_{filename}"

            supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
            secret_key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
            service_role_key = os.getenv(
                "SUPABASE_SERVICE_ROLE_KEY", ""
            ).strip()

            if not supabase_url or not secret_key or not service_role_key:
                return (
                    "Supabase credentials are missing. "
                    "Check SUPABASE_URL, SUPABASE_SECRET_KEY and "
                    "SUPABASE_SERVICE_ROLE_KEY in backend/.env."
                )

            upload_url = (
                f"{supabase_url}/storage/v1/object/"
                f"complaint-images/{filename}"
            )

            try:
                response = requests.post(
                    upload_url,
                    headers={
                        "apikey": secret_key,
                        "Authorization": f"Bearer {service_role_key}",
                        "Content-Type": (
                            image.mimetype or "application/octet-stream"
                        ),
                        
                    },
                    data=image.read(),
                    timeout=30
                )

                response.raise_for_status()

                image_url = (
                    f"{supabase_url}/storage/v1/object/public/"
                    f"complaint-images/{filename}"
                )

            except requests.RequestException as error:
                print("SUPABASE IMAGE UPLOAD ERROR:", error)

                if error.response is not None:
                    print("SUPABASE RESPONSE:", error.response.text)
                    return (
                        "Image upload failed. Supabase says: "
                        + error.response.text
                    )

                return (
                    "Image upload failed. "
                    "Please check your internet connection."
                )

        # Save complaint details and image URL in database
        connection = get_db_connection()

        try:
            connection.execute(
                """
                INSERT INTO complaints
                (user_id, title, description, category, location, image)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    session["user_id"],
                    title,
                    description,
                    category,
                    location,
                    image_url
                )
            )

            connection.commit()

        finally:
            connection.close()

        return redirect(url_for("complaints"))

    return render_template("report.html")


# Citizen's complaints
@app.route("/complaints")
def complaints():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    try:
        user_complaints = connection.execute(
            """
            SELECT * FROM complaints
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (session["user_id"],)
        ).fetchall()

    finally:
        connection.close()

    return render_template(
        "complaints.html",
        complaints=user_complaints
    )


# Citizen logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# Admin login
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        admin_email = os.environ.get(
            "ADMIN_EMAIL", "admin@civicconnect.com"
        )

        admin_password = os.environ.get(
            "ADMIN_PASSWORD", "Admin@123"
        )

        if email == admin_email and password == admin_password:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))

        return "Invalid email or password."

    return render_template("admin-login.html")


# Admin dashboard
@app.route("/admin-dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    return render_template("admin-dashboard.html")


# View all complaints
@app.route("/manage-complaints")
def manage_complaints():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    connection = get_db_connection()

    try:
        all_complaints = connection.execute(
            """
            SELECT complaints.*,
                   users.name AS citizen_name,
                   users.email AS citizen_email
            FROM complaints
            JOIN users ON complaints.user_id = users.id
            ORDER BY complaints.id DESC
            """
        ).fetchall()

    finally:
        connection.close()

    return render_template(
        "manage-complaints.html",
        complaints=all_complaints
    )


# Update complaint status
@app.route("/update-status/<int:complaint_id>", methods=["POST"])
def update_status(complaint_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    status = request.form.get("status")

    allowed_statuses = [
        "Pending",
        "In Progress",
        "Resolved"
    ]

    if status not in allowed_statuses:
        return "Invalid status."

    connection = get_db_connection()

    try:
        connection.execute(
            """
            UPDATE complaints
            SET status = %s
            WHERE id = %s
            """,
            (status, complaint_id)
        )

        connection.commit()

    finally:
        connection.close()

    return redirect(url_for("manage_complaints"))


# Admin logout
@app.route("/admin-logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


# Run application
if __name__ == "__main__":
    app.run(debug=True)
