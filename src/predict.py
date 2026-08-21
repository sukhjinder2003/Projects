import os
import joblib
import pandas as pd


class EmployeeRetentionPredictor:

    def __init__(self):

        self.model_path = os.path.join(
            "models",
            "best_model.pkl"
        )

        self.preprocessor_path = os.path.join(
            "models",
            "preprocessor.pkl"
        )

        self.threshold_path = os.path.join(
            "models",
            "best_threshold.pkl"
        )

        # Load model
        self.model = joblib.load(
            self.model_path
        )

        # Load preprocessor
        self.preprocessor = joblib.load(
            self.preprocessor_path
        )

        # Load optimized threshold
        self.threshold = joblib.load(
            self.threshold_path
        )

        print("Model loaded successfully.")
        print(
            f"Prediction threshold: "
            f"{self.threshold:.2f}"
        )

    def predict(self, input_data):

        """
        input_data should be a dictionary
        containing employee details.
        """

        # Convert dictionary to DataFrame
        input_df = pd.DataFrame(
            [input_data]
        )

        # Transform data
        transformed_data = (
            self.preprocessor.transform(
                input_df
            )
        )

        # Get probability of Attrition = Yes
        probability = (
            self.model.predict_proba(
                transformed_data
            )[0][1]
        )

        # Apply optimized threshold
        prediction = (
            1
            if probability >= self.threshold
            else 0
        )

        # Convert prediction to readable result
        result = (
            "Attrition"
            if prediction == 1
            else "No Attrition"
        )

        return {
            "prediction": result,
            "attrition_probability": round(
                probability * 100,
                2
            ),
            "threshold_used": round(
                self.threshold,
                2
            )
        }


if __name__ == "__main__":

    predictor = EmployeeRetentionPredictor()

    # Sample employee data
    employee_data = {

        "Age": 35,
        "BusinessTravel": "Travel_Rarely",
        "DailyRate": 800,
        "Department": "Sales",
        "DistanceFromHome": 10,
        "Education": 3,
        "EducationField": "Life Sciences",
        "EnvironmentSatisfaction": 3,
        "Gender": "Male",
        "HourlyRate": 70,
        "JobInvolvement": 3,
        "JobLevel": 2,
        "JobRole": "Sales Executive",
        "JobSatisfaction": 3,
        "MaritalStatus": "Married",
        "MonthlyIncome": 5000,
        "MonthlyRate": 15000,
        "NumCompaniesWorked": 2,
        "OverTime": "No",
        "PercentSalaryHike": 15,
        "PerformanceRating": 3,
        "RelationshipSatisfaction": 3,
        "StockOptionLevel": 1,
        "TotalWorkingYears": 10,
        "TrainingTimesLastYear": 3,
        "WorkLifeBalance": 3,
        "YearsAtCompany": 5,
        "YearsInCurrentRole": 3,
        "YearsSinceLastPromotion": 2,
        "YearsWithCurrManager": 3
    }

    result = predictor.predict(
        employee_data
    )

    print("\nPrediction Result")
    print("-" * 40)

    print(
        f"Prediction: "
        f"{result['prediction']}"
    )

    print(
        f"Attrition Probability: "
        f"{result['attrition_probability']}%"
    )

    print(
        f"Threshold Used: "
        f"{result['threshold_used']}"
    )