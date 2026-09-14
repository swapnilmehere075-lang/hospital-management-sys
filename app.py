from flask import Flask, render_template, request, redirect, url_for
import mysql.connector

app = Flask(__name__, template_folder="templates")

import os

def get_db_connection():
    return mysql.connector.connect(
        host=os.environ["MYSQLHOST"],
        port=int(os.environ["MYSQLPORT"]),
        user=os.environ["MYSQLUSER"],
        password=os.environ["MYSQLPASSWORD"],
        database=os.environ["MYSQLDATABASE"]
    )

@app.route("/")
def home():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM patient")
    total_patients = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM appointment")
    total_appointments = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM billing")
    total_bills = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM department")
    total_departments = cursor.fetchone()["total"]

    cursor.close()
    db.close()

    return render_template(
        "index.html",
        total_patients=total_patients,
        total_appointments=total_appointments,
        total_bills=total_bills,
        total_departments=total_departments
    )

@app.route("/register", methods=["POST"])
def register():
    first_name = request.form.get("first_name")
    last_name = request.form.get("last_name")
    gender = request.form.get("gender")
    date_of_birth = request.form.get("date_of_birth") or None
    phone = request.form.get("phone")
    address = request.form.get("address")
    blood_group = request.form.get("blood_group")

    if not first_name or not last_name or not phone or not address:
        return "Please fill all required patient fields."

    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute(
        """
        INSERT INTO Patient
        (first_name,last_name,gender,date_of_birth,phone,address,blood_group)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            first_name,
            last_name,
            gender,
            date_of_birth,
            phone,
            address,
            blood_group
        )
    )

    db.commit()

    cursor.close()
    db.close()

    return redirect(url_for("home"))

@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    patients = []

    if q:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        if q.isdigit():
            cursor.execute(
                """
                SELECT *
                FROM Patient
                WHERE patient_id = %s
                """,
                (int(q),)
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM Patient
                WHERE first_name LIKE %s
                OR last_name LIKE %s
                ORDER BY patient_id DESC
                """,
                (f"%{q}%", f"%{q}%")
            )

        patients = cursor.fetchall()

        cursor.close()
        db.close()

    return render_template(
        "search.html",
        patients=patients,
        search=q
    )

@app.route("/patient/<int:patient_id>")
def view_patient(patient_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT *
        FROM Patient
        WHERE patient_id = %s
        """,
        (patient_id,)
    )

    patient = cursor.fetchone()

    if not patient:
        cursor.close()
        db.close()
        return "Patient not found."

    cursor.execute(
        """
        SELECT
            a.appointment_id,
            a.appointment_date,
            a.appointment_time,
            a.status,
            a.reason,
            CONCAT(d.first_name,' ',d.last_name) AS doctor_name,
            d.specialization
        FROM Appointment a
        JOIN Doctor d
        ON a.doctor_id = d.doctor_id
        WHERE a.patient_id = %s
        ORDER BY a.appointment_id DESC
        """,
        (patient_id,)
    )

    appointments = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            b.bill_id,
            b.appointment_id,
            b.amount,
            b.payment_status,
            b.bill_date,
            b.payment_method
        FROM billing b
        WHERE b.patient_id = %s
        ORDER BY b.bill_id DESC
        """,
        (patient_id,)
    )

    bills = cursor.fetchall()

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount),0) AS total_bill
        FROM Billing
        WHERE patient_id = %s
        """,
        (patient_id,)
    )

    total_bill = cursor.fetchone()["total_bill"]

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount),0) AS pending_amount
        FROM Billing
        WHERE patient_id = %s
        AND payment_status = 'Pending'
        """,
        (patient_id,)
    )

    pending_amount = cursor.fetchone()["pending_amount"]

    cursor.close()
    db.close()

    return render_template(
        "patient.html",
        patient=patient,
        appointments=appointments,
        bills=bills,
        total_bill=total_bill,
        pending_amount=pending_amount
    )

@app.route("/appointment", methods=["GET", "POST"])
def appointment():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    message = None
    error = None

    if request.method == "POST":
        patient_id = request.form.get("patient_id")
        doctor_id = request.form.get("doctor_id")
        appointment_date = request.form.get("appointment_date")
        appointment_time = request.form.get("appointment_time")
        reason = request.form.get("reason")

        cursor.execute(
            "SELECT patient_id FROM Patient WHERE patient_id = %s",
            (patient_id,)
        )

        patient_exists = cursor.fetchone()

        cursor.execute(
            "SELECT doctor_id FROM Doctor WHERE doctor_id = %s",
            (doctor_id,)
        )

        doctor_exists = cursor.fetchone()

        if not patient_exists:
            error = "Selected patient does not exist."
        elif not doctor_exists:
            error = "Selected doctor does not exist."
        else:
            cursor.execute(
                """
                SELECT appointment_id
                FROM Appointment
                WHERE doctor_id = %s
                AND appointment_date = %s
                AND appointment_time = %s
                """,
                (
                    doctor_id,
                    appointment_date,
                    appointment_time
                )
            )

            existing = cursor.fetchone()

            if existing:
                error = "This doctor already has an appointment at this date and time."
            else:
                cursor.execute(
                    """
                    INSERT INTO Appointment
                    (patient_id,doctor_id,appointment_date,appointment_time,status,reason)
                    VALUES (%s,%s,%s,%s,'Scheduled',%s)
                    """,
                    (
                        patient_id,
                        doctor_id,
                        appointment_date,
                        appointment_time,
                        reason
                    )
                )

                db.commit()
                message = "Appointment booked successfully."

    cursor.execute(
        """
        SELECT
            patient_id,
            first_name,
            last_name
        FROM Patient
        ORDER BY patient_id DESC
        """
    )

    patients = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            doctor_id,
            first_name,
            last_name,
            specialization
        FROM Doctor
        ORDER BY first_name
        """
    )

    doctors = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            a.appointment_id,
            a.patient_id,
            CONCAT(p.first_name,' ',p.last_name) AS patient_name,
            CONCAT(d.first_name,' ',d.last_name) AS doctor_name,
            d.specialization,
            a.appointment_date,
            a.appointment_time,
            a.status,
            a.reason
        FROM Appointment a
        JOIN Patient p
        ON a.patient_id = p.patient_id
        JOIN Doctor d
        ON a.doctor_id = d.doctor_id
        ORDER BY a.appointment_id DESC
        """
    )

    appointments = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "appointment.html",
        patients=patients,
        doctors=doctors,
        appointments=appointments,
        message=message,
        error=error
    )

@app.route("/billing", methods=["GET", "POST"])
def billing():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    message = None
    error = None

    if request.method == "POST":
        patient_id = request.form.get("patient_id")
        appointment_id = request.form.get("appointment_id")
        amount = request.form.get("amount")
        payment_status = request.form.get("payment_status")
        payment_method = request.form.get("payment_method")
        bill_date = request.form.get("bill_date")

        cursor.execute(
            "SELECT patient_id FROM Patient WHERE patient_id = %s",
            (patient_id,)
        )

        patient_exists = cursor.fetchone()

        cursor.execute(
            """
            SELECT appointment_id
            FROM Appointment
            WHERE appointment_id = %s
            AND patient_id = %s
            """,
            (
                appointment_id,
                patient_id
            )
        )

        appointment_exists = cursor.fetchone()

        if not patient_exists:
            error = "Selected patient does not exist."
        elif not appointment_exists:
            error = "Selected appointment does not belong to this patient."
        elif not amount or float(amount) <= 0:
            error = "Billing amount must be greater than zero."
        else:
            cursor.execute(
                """
                INSERT INTO Billing
                (patient_id,appointment_id,amount,payment_status,bill_date,payment_method)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    patient_id,
                    appointment_id,
                    amount,
                    payment_status,
                    bill_date,
                    payment_method
                )
            )

            db.commit()
            message = "Bill created successfully."

    cursor.execute(
        """
        SELECT
            patient_id,
            first_name,
            last_name
        FROM Patient
        ORDER BY patient_id DESC
        """
    )

    patients = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            a.appointment_id,
            a.patient_id,
            CONCAT(p.first_name,' ',p.last_name) AS patient_name,
            a.appointment_date,
            a.appointment_time
        FROM Appointment a
        JOIN Patient p
        ON a.patient_id = p.patient_id
        ORDER BY a.appointment_id DESC
        """
    )

    billing_appointments = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            b.bill_id,
            b.patient_id,
            CONCAT(p.first_name,' ',p.last_name) AS patient_name,
            b.appointment_id,
            b.amount,
            b.payment_status,
            b.bill_date,
            b.payment_method
        FROM Billing b
        JOIN Patient p
        ON b.patient_id = p.patient_id
        ORDER BY b.bill_id DESC
        """
    )

    bills = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "billing.html",
        patients=patients,
        billing_appointments=billing_appointments,
        bills=bills,
        message=message,
        error=error
    )

@app.route("/doctors")
def doctors():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            d.doctor_id,
            CONCAT(d.first_name,' ',d.last_name) AS doctor_name,
            d.specialization,
            d.phone,
            dep.department_name,
            dep.location
        FROM Doctor d
        LEFT JOIN Department dep
        ON d.department_id = dep.department_id
        ORDER BY d.doctor_id
        """
    )

    doctors_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "doctors.html",
        doctors=doctors_list
    )

@app.route("/departments")
def departments():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            department_id,
            department_name,
            location
        FROM Department
        ORDER BY department_id
        """
    )

    departments_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "departments.html",
        departments=departments_list
    )

if __name__ == "__main__":
    app.run(debug=True)