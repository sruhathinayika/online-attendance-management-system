"""
Online Attendance Management System

Packages: streamlit, pandas, numpy

Run: py -m streamlit run app.py
"""

import os
import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv


# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

TEACHER_PASSWORD = os.getenv("TEACHER_PASSWORD", "admin123")

STATUSES = ["Present", "Absent", "Late", "Excused"]

BASE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE, "attendance.db")


# =========================================================
# DATABASE
# =========================================================

def get_connection():
    """Create database and tables if they don't exist."""

    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            class_name TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            date TEXT NOT NULL,
            student_id TEXT NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY (date, student_id),
            FOREIGN KEY (student_id)
                REFERENCES students(student_id)
        )
    """)

    conn.commit()

    return conn


# Create database when application starts
get_connection()


# =========================================================
# STUDENT FUNCTIONS
# =========================================================

def load_students():
    """Load all students from SQLite."""

    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT student_id, name, class_name
        FROM students
        ORDER BY student_id
        """,
        conn
    )

    conn.close()

    return df


def add_student(student_id, name, class_name):
    """Add a new student."""

    conn = get_connection()

    try:
        conn.execute(
            """
            INSERT INTO students
            (student_id, name, class_name)
            VALUES (?, ?, ?)
            """,
            (student_id, name, class_name)
        )

        conn.commit()

        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        conn.close()


def delete_student(student_id):
    """Delete student and their attendance records."""

    conn = get_connection()

    conn.execute(
        "DELETE FROM attendance WHERE student_id = ?",
        (student_id,)
    )

    conn.execute(
        "DELETE FROM students WHERE student_id = ?",
        (student_id,)
    )

    conn.commit()
    conn.close()


# =========================================================
# ATTENDANCE FUNCTIONS
# =========================================================

def load_attendance():
    """Load attendance records from SQLite."""

    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT date, student_id, status
        FROM attendance
        ORDER BY date, student_id
        """,
        conn
    )

    conn.close()

    return df


def save_attendance(day, rows):
    """
    Save attendance.

    If attendance already exists for the same
    date and student, it will be updated.
    """

    conn = get_connection()

    day_string = day.isoformat()

    for _, row in rows.iterrows():

        conn.execute(
            """
            INSERT INTO attendance
            (date, student_id, status)
            VALUES (?, ?, ?)

            ON CONFLICT(date, student_id)
            DO UPDATE SET status = excluded.status
            """,
            (
                day_string,
                str(row["student_id"]),
                str(row["status"])
            )
        )

    conn.commit()
    conn.close()


# =========================================================
# ATTENDANCE SUMMARY
# =========================================================

def summary(attendance, students):
    """
    Calculate attendance percentage for each student.

    Present + Late = attended
    Excused = ignored in total
    """

    if attendance.empty or students.empty:
        return pd.DataFrame()

    counts = pd.crosstab(
        attendance["student_id"],
        attendance["status"]
    )

    # Make sure all status columns exist
    for status in STATUSES:

        if status not in counts.columns:
            counts[status] = 0

    counts = counts[STATUSES].reset_index()

    output = students.merge(
        counts,
        on="student_id",
        how="inner"
    )

    attended = (
        output["Present"] +
        output["Late"]
    ).to_numpy(dtype=float)

    total = (
        output[STATUSES].sum(axis=1) -
        output["Excused"]
    ).to_numpy(dtype=float)

    output["Attendance %"] = np.where(
        total > 0,
        attended / np.where(total == 0, 1, total) * 100,
        0
    ).round(1)

    return output


# =========================================================
# LOGIN PAGE
# =========================================================

def login_page():

    st.title("🗓️ Attendance Management System")

    tab1, tab2 = st.tabs(
        ["Teacher Login", "Student View"]
    )

    # ---------------- Teacher login ----------------

    with tab1:

        password = st.text_input(
            "Teacher Password",
            type="password"
        )

        if st.button(
            "Login",
            type="primary"
        ):

            if password == TEACHER_PASSWORD:

                st.session_state.role = "teacher"

                st.rerun()

            else:

                st.error("Wrong password")

    # ---------------- Student login ----------------

    with tab2:

        student_id = st.text_input(
            "Enter your Student ID"
        ).strip()

        if st.button("View My Attendance"):

            students = load_students()

            if student_id in students["student_id"].values:

                st.session_state.role = "student"

                st.session_state.sid = student_id

                st.rerun()

            else:

                st.error("Student ID not found")


# =========================================================
# DASHBOARD
# =========================================================

def dashboard_page():

    st.header("📊 Dashboard")

    students = load_students()
    attendance = load_attendance()

    today = attendance[
        attendance["date"] == date.today().isoformat()
    ]

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Total Students",
        len(students)
    )

    col2.metric(
        "Marked Today",
        len(today)
    )

    if len(today):

        present_percentage = (
            today["status"]
            .isin(["Present", "Late"])
            .mean()
            * 100
        )

        col3.metric(
            "Present Today",
            f"{present_percentage:.0f}%"
        )

    else:

        col3.metric(
            "Present Today",
            "—"
        )

    if attendance.empty:

        st.info(
            "No attendance yet. "
            "Add students, then mark attendance."
        )

        return

    # ---------------- Daily attendance chart ----------------

    st.subheader("📈 Daily Attendance %")

    daily = (
        attendance
        .assign(
            attended=attendance["status"]
            .isin(["Present", "Late"])
        )
        .groupby("date")["attended"]
        .mean()
        * 100
    )

    st.line_chart(daily)

    # ---------------- Students below 75% ----------------

    st.subheader("⚠️ Below 75% Attendance")

    result = summary(
        attendance,
        students
    )

    if result.empty:

        st.info("No attendance summary available.")

        return

    low_attendance = result[
        result["Attendance %"] < 75
    ]

    if low_attendance.empty:

        st.success(
            "Everyone is above 75% 🎉"
        )

    else:

        st.dataframe(
            low_attendance,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# STUDENTS PAGE
# =========================================================

def students_page():

    st.header("🎓 Students")

    # ---------------- Add student ----------------

    with st.form(
        "add_student",
        clear_on_submit=True
    ):

        col1, col2, col3 = st.columns(3)

        student_id = col1.text_input(
            "Student ID"
        )

        name = col2.text_input(
            "Name"
        )

        class_name = col3.text_input(
            "Class (e.g. 10-A)"
        )

        submitted = st.form_submit_button(
            "➕ Add Student",
            type="primary"
        )

        if submitted:

            student_id = student_id.strip()
            name = name.strip()
            class_name = class_name.strip()

            if not (
                student_id
                and name
                and class_name
            ):

                st.error(
                    "Please fill all fields."
                )

            elif add_student(
                student_id,
                name,
                class_name
            ):

                st.success(
                    f"Added {name}"
                )

                st.rerun()

            else:

                st.error(
                    "This Student ID already exists."
                )

    # ---------------- Display students ----------------

    students = load_students()

    st.subheader("📋 Student List")

    st.dataframe(
        students,
        use_container_width=True,
        hide_index=True
    )

    # ---------------- Delete student ----------------

    if not students.empty:

        options = (
            students["student_id"]
            + " - "
            + students["name"]
        )

        target = st.selectbox(
            "Select Student to Delete",
            options
        )

        if st.button("🗑️ Delete Student"):

            student_id = target.split(
                " - ",
                1
            )[0]

            delete_student(student_id)

            st.success(
                "Student deleted successfully."
            )

            st.rerun()


# =========================================================
# MARK ATTENDANCE PAGE
# =========================================================

def mark_page():

    st.header("✅ Mark Attendance")

    students = load_students()

    if students.empty:

        st.info(
            "Add students first."
        )

        return

    col1, col2 = st.columns(2)

    class_name = col1.selectbox(
        "Class",
        sorted(
            students["class_name"].unique()
        )
    )

    selected_date = col2.date_input(
        "Date",
        value=date.today(),
        max_value=date.today()
    )

    # Students belonging to selected class

    table = students[
        students["class_name"] == class_name
    ][
        ["student_id", "name"]
    ].reset_index(drop=True)

    # Existing attendance

    attendance = load_attendance()

    old = attendance[
        attendance["date"] ==
        selected_date.isoformat()
    ]

    if not old.empty:

        old = old.set_index(
            "student_id"
        )["status"]

        table["status"] = (
            table["student_id"]
            .map(old)
            .fillna("Present")
        )

    else:

        table["status"] = "Present"

    # ---------------- Editable attendance table ----------------

    edited = st.data_editor(

        table,

        hide_index=True,

        use_container_width=True,

        disabled=[
            "student_id",
            "name"
        ],

        column_config={

            "status":
                st.column_config.SelectboxColumn(
                    "Status",
                    options=STATUSES,
                    required=True
                )
        },

        key=f"editor_{class_name}_{selected_date}"
    )

    # ---------------- Save ----------------

    if st.button(
        "💾 Save Attendance",
        type="primary"
    ):

        save_attendance(
            selected_date,
            edited
        )

        st.success(
            f"Saved attendance for "
            f"{len(edited)} students on "
            f"{selected_date}"
        )


# =========================================================
# REPORTS PAGE
# =========================================================

def reports_page():

    st.header("📈 Reports")

    students = load_students()
    attendance = load_attendance()

    if attendance.empty:

        st.info(
            "No attendance data available."
        )

        return

    col1, col2 = st.columns(2)

    start_date = col1.date_input(
        "From",
        value=date.today() -
        timedelta(days=30)
    )

    end_date = col2.date_input(
        "To",
        value=date.today()
    )

    # Filter attendance

    attendance = attendance[
        (attendance["date"] >= start_date.isoformat())
        &
        (attendance["date"] <= end_date.isoformat())
    ]

    result = summary(
        attendance,
        students
    )

    if result.empty:

        st.warning(
            "No records in this date range."
        )

        return

    # ---------------- Attendance table ----------------

    st.dataframe(

        result,

        use_container_width=True,

        hide_index=True,

        column_config={

            "Attendance %":
                st.column_config.ProgressColumn(

                    "Attendance %",

                    min_value=0,

                    max_value=100,

                    format="%.1f%%"
                )
        }
    )

    # ---------------- Chart ----------------

    st.subheader(
        "📊 Student Attendance"
    )

    st.bar_chart(
        result.set_index("name")[
            "Attendance %"
        ]
    )

    # ---------------- Download report ----------------

    report_csv = result.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(

        "⬇️ Download Attendance Report",

        report_csv,

        file_name="attendance_report.csv",

        mime="text/csv"
    )


# =========================================================
# STUDENT VIEW PAGE
# =========================================================

def student_page():

    student_id = st.session_state.sid

    students = load_students()

    student = students[
        students["student_id"] == student_id
    ]

    if student.empty:

        st.error(
            "Student account not found."
        )

        return

    student = student.iloc[0]

    st.header(
        f"Hello, {student['name']} 👋"
    )

    st.caption(
        f"Class: {student['class_name']} | "
        f"ID: {student_id}"
    )

    attendance = load_attendance()

    my_attendance = attendance[
        attendance["student_id"] ==
        student_id
    ].sort_values(
        "date",
        ascending=False
    )

    if my_attendance.empty:

        st.info(
            "No attendance recorded yet."
        )

        return

    result = summary(
        my_attendance,
        students
    )

    if result.empty:

        st.info(
            "No attendance summary available."
        )

        return

    student_summary = result.iloc[0]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Attendance",
        f"{student_summary['Attendance %']}%"
    )

    col2.metric(
        "Present",
        int(student_summary["Present"])
    )

    col3.metric(
        "Late",
        int(student_summary["Late"])
    )

    col4.metric(
        "Absent",
        int(student_summary["Absent"])
    )

    if student_summary["Attendance %"] < 75:

        st.warning(
            "Your attendance is below 75%."
        )

    else:

        st.success(
            "Your attendance is above 75% 🎉"
        )

    st.subheader(
        "📅 Attendance History"
    )

    st.dataframe(
        my_attendance[
            ["date", "status"]
        ],
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# MAIN APPLICATION
# =========================================================

role = st.session_state.get(
    "role"
)

if not role:

    login_page()

else:

    with st.sidebar:

        st.title(
            "🗓️ Attendance"
        )

        st.caption(
            f"Logged in as {role}"
        )

        if role == "teacher":

            page = st.radio(
                "Menu",
                [
                    "Dashboard",
                    "Mark Attendance",
                    "Students",
                    "Reports"
                ]
            )

        if st.button("Logout"):

            st.session_state.clear()

            st.rerun()

    # ---------------- Student ----------------

    if role == "student":

        student_page()

    # ---------------- Teacher ----------------

    else:
        pages = {
            "Dashboard": dashboard_page,
            "Mark Attendance": mark_page,
            "Students": students_page,
            "Reports": reports_page
        }

        pages[page]()
               