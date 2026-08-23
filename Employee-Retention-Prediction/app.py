from flask import Flask, render_template, request
from src.predict import EmployeeRetentionPredictor

app = Flask(__name__)

# Load model once when application starts
predictor = EmployeeRetentionPredictor()


@app.route("/", methods=["GET", "POST"])
def home():

    result = None

    if request.method == "POST":
        try:
            employee_data = {
                "Age": int(request.form["Age"]),
                "BusinessTravel": request.form["BusinessTravel"],
                "DailyRate": int(request.form["DailyRate"]),
                "Department": request.form["Department"],
                "DistanceFromHome": int(request.form["DistanceFromHome"]),
                "Education": int(request.form["Education"]),
                "EducationField": request.form["EducationField"],
                "EnvironmentSatisfaction": int(request.form["EnvironmentSatisfaction"]),
                "Gender": request.form["Gender"],
                "HourlyRate": int(request.form["HourlyRate"]),
                "JobInvolvement": int(request.form["JobInvolvement"]),
                "JobLevel": int(request.form["JobLevel"]),
                "JobRole": request.form["JobRole"],
                "JobSatisfaction": int(request.form["JobSatisfaction"]),
                "MaritalStatus": request.form["MaritalStatus"],
                "MonthlyIncome": int(request.form["MonthlyIncome"]),
                "MonthlyRate": int(request.form["MonthlyRate"]),
                "NumCompaniesWorked": int(request.form["NumCompaniesWorked"]),
                "OverTime": request.form["OverTime"],
                "PercentSalaryHike": int(request.form["PercentSalaryHike"]),
                "PerformanceRating": int(request.form["PerformanceRating"]),
                "RelationshipSatisfaction": int(
                    request.form["RelationshipSatisfaction"]
                ),
                "StockOptionLevel": int(request.form["StockOptionLevel"]),
                "TotalWorkingYears": int(request.form["TotalWorkingYears"]),
                "TrainingTimesLastYear": int(request.form["TrainingTimesLastYear"]),
                "WorkLifeBalance": int(request.form["WorkLifeBalance"]),
                "YearsAtCompany": int(request.form["YearsAtCompany"]),
                "YearsInCurrentRole": int(request.form["YearsInCurrentRole"]),
                "YearsSinceLastPromotion": int(request.form["YearsSinceLastPromotion"]),
                "YearsWithCurrManager": int(request.form["YearsWithCurrManager"]),
            }

            result = predictor.predict(employee_data)

        except Exception as e:
            result = {"error": str(e)}

    return render_template("index.html", result=result)


if __name__ == "__main__":
    app.run(debug=True)
