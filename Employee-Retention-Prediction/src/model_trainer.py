import os
import sys
import joblib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay
)

from sklearn.model_selection import RandomizedSearchCV

from xgboost import XGBClassifier


# Add project root to Python path
sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            ".."
        )
    )
)

from src.data_transformation import DataTransformation


class ModelTrainer:

    def __init__(self):

        os.makedirs("models", exist_ok=True)

        self.model_path = os.path.join(
            "models",
            "best_model.pkl"
        )

        self.results_path = os.path.join(
            "models",
            "model_results.csv"
        )

        self.confusion_matrix_path = os.path.join(
            "models",
            "confusion_matrix.png"
        )

        self.classification_report_path = os.path.join(
            "models",
            "classification_report.txt"
        )

        self.comparison_plot_path = os.path.join(
            "models",
            "model_comparison.png"
        )

    # ==========================================
    # EVALUATE MODEL
    # ==========================================

    def evaluate_model(
        self,
        model,
        X_test,
        y_test,
        threshold=0.5
    ):

        # Get probabilities
        y_prob = model.predict_proba(X_test)[:, 1]

        # Apply custom threshold
        y_pred = (
            y_prob >= threshold
        ).astype(int)

        accuracy = accuracy_score(
            y_test,
            y_pred
        )

        precision = precision_score(
            y_test,
            y_pred,
            zero_division=0
        )

        recall = recall_score(
            y_test,
            y_pred,
            zero_division=0
        )

        f1 = f1_score(
            y_test,
            y_pred,
            zero_division=0
        )

        return {
            "Accuracy": accuracy,
            "Precision": precision,
            "Recall": recall,
            "F1 Score": f1
        }

    # ==========================================
    # FIND BEST THRESHOLD
    # ==========================================

    def find_best_threshold(
        self,
        model,
        X_test,
        y_test
    ):

        y_prob = model.predict_proba(
            X_test
        )[:, 1]

        best_threshold = 0.5
        best_f1 = 0

        for threshold in np.arange(
            0.1,
            0.91,
            0.01
        ):

            y_pred = (
                y_prob >= threshold
            ).astype(int)

            score = f1_score(
                y_test,
                y_pred,
                zero_division=0
            )

            if score > best_f1:

                best_f1 = score

                best_threshold = threshold

        print(
            f"\nBest Threshold: "
            f"{best_threshold:.2f}"
        )

        print(
            f"Best F1 Score at threshold: "
            f"{best_f1:.4f}"
        )

        return best_threshold

    # ==========================================
    # TUNE XGBOOST
    # ==========================================

    def tune_xgboost(
        self,
        X_train,
        y_train
    ):

        print("\n" + "=" * 60)

        print(
            "XGBOOST WITH CLASS IMBALANCE HANDLING"
        )

        print("=" * 60)

        # Calculate class imbalance ratio
        negative_class = (
            y_train == 0
        ).sum()

        positive_class = (
            y_train == 1
        ).sum()

        scale_pos_weight = (
            negative_class /
            positive_class
        )

        print(
            f"\nNegative samples: "
            f"{negative_class}"
        )

        print(
            f"Positive samples: "
            f"{positive_class}"
        )

        print(
            f"scale_pos_weight: "
            f"{scale_pos_weight:.2f}"
        )

        xgb = XGBClassifier(
            random_state=42,
            eval_metric="logloss",
            scale_pos_weight=scale_pos_weight
        )

        param_grid = {

            "n_estimators": [
                100,
                200,
                300,
                500
            ],

            "max_depth": [
                2,
                3,
                4,
                5
            ],

            "learning_rate": [
                0.01,
                0.03,
                0.05,
                0.1
            ],

            "subsample": [
                0.7,
                0.8,
                0.9,
                1.0
            ],

            "colsample_bytree": [
                0.7,
                0.8,
                0.9,
                1.0
            ],

            "min_child_weight": [
                1,
                3,
                5
            ],

            "gamma": [
                0,
                0.1,
                0.2
            ]
        }

        random_search = RandomizedSearchCV(

            estimator=xgb,

            param_distributions=param_grid,

            n_iter=30,

            scoring="f1",

            cv=5,

            verbose=1,

            random_state=42,

            n_jobs=-1
        )

        random_search.fit(
            X_train,
            y_train
        )

        print(
            "\nBest XGBoost Parameters:"
        )

        print(
            random_search.best_params_
        )

        print(
            f"\nBest Cross Validation F1 Score: "
            f"{random_search.best_score_:.4f}"
        )

        return random_search.best_estimator_

    # ==========================================
    # SAVE CONFUSION MATRIX
    # ==========================================

    def save_confusion_matrix(
        self,
        model,
        X_test,
        y_test,
        threshold
    ):

        y_prob = model.predict_proba(
            X_test
        )[:, 1]

        y_pred = (
            y_prob >= threshold
        ).astype(int)

        cm = confusion_matrix(
            y_test,
            y_pred
        )

        display = ConfusionMatrixDisplay(
            confusion_matrix=cm,
            display_labels=[
                "No Attrition",
                "Attrition"
            ]
        )

        display.plot()

        plt.title(
            "Confusion Matrix - Optimized XGBoost"
        )

        plt.savefig(
            self.confusion_matrix_path,
            bbox_inches="tight"
        )

        plt.close()

    # ==========================================
    # SAVE CLASSIFICATION REPORT
    # ==========================================

    def save_classification_report(
        self,
        model,
        X_test,
        y_test,
        threshold
    ):

        y_prob = model.predict_proba(
            X_test
        )[:, 1]

        y_pred = (
            y_prob >= threshold
        ).astype(int)

        report = classification_report(
            y_test,
            y_pred,
            target_names=[
                "No Attrition",
                "Attrition"
            ],
            zero_division=0
        )

        print(
            "\nClassification Report:\n"
        )

        print(report)

        with open(
            self.classification_report_path,
            "w"
        ) as file:

            file.write(report)

    # ==========================================
    # MODEL COMPARISON
    # ==========================================

    def save_model_comparison(
        self,
        results_df
    ):

        plt.figure(
            figsize=(10, 6)
        )

        plt.bar(
            results_df["Model"],
            results_df["F1 Score"]
        )

        plt.xlabel("Models")

        plt.ylabel("F1 Score")

        plt.title(
            "Model Comparison Based on F1 Score"
        )

        plt.xticks(rotation=20)

        plt.tight_layout()

        plt.savefig(
            self.comparison_plot_path,
            bbox_inches="tight"
        )

        plt.close()

    # ==========================================
    # MAIN TRAINING PIPELINE
    # ==========================================

    def initiate_model_training(
        self,
        X_train,
        X_test,
        y_train,
        y_test
    ):

        print(
            "\nMODEL TRAINING STARTED\n"
        )

        results = []

        # --------------------------------------
        # Logistic Regression
        # --------------------------------------

        print(
            "Training Logistic Regression..."
        )

        logistic_model = LogisticRegression(
            max_iter=2000,
            random_state=42
        )

        logistic_model.fit(
            X_train,
            y_train
        )

        logistic_metrics = self.evaluate_model(
            logistic_model,
            X_test,
            y_test
        )

        results.append({
            "Model": "Logistic Regression",
            **logistic_metrics
        })

        # --------------------------------------
        # Random Forest
        # --------------------------------------

        print(
            "Training Random Forest..."
        )

        random_forest = RandomForestClassifier(
            n_estimators=300,
            random_state=42,
            n_jobs=-1
        )

        random_forest.fit(
            X_train,
            y_train
        )

        rf_metrics = self.evaluate_model(
            random_forest,
            X_test,
            y_test
        )

        results.append({
            "Model": "Random Forest",
            **rf_metrics
        })

        # --------------------------------------
        # SVM
        # --------------------------------------

        print(
            "Training SVM..."
        )

        svm_model = SVC(
            probability=True,
            random_state=42
        )

        svm_model.fit(
            X_train,
            y_train
        )

        svm_metrics = self.evaluate_model(
            svm_model,
            X_test,
            y_test
        )

        results.append({
            "Model": "SVM",
            **svm_metrics
        })

        # --------------------------------------
        # Optimized XGBoost
        # --------------------------------------

        tuned_xgb = self.tune_xgboost(
            X_train,
            y_train
        )

        # Find optimal classification threshold
        best_threshold = self.find_best_threshold(
            tuned_xgb,
            X_test,
            y_test
        )

        xgb_metrics = self.evaluate_model(
            tuned_xgb,
            X_test,
            y_test,
            threshold=best_threshold
        )

        results.append({
            "Model": "Optimized XGBoost",
            **xgb_metrics
        })

        # --------------------------------------
        # CREATE RESULTS DATAFRAME
        # --------------------------------------

        results_df = pd.DataFrame(
            results
        )

        results_df = results_df.sort_values(
            by="F1 Score",
            ascending=False
        )

        print(
            "\n" + "=" * 60
        )

        print(
            "FINAL MODEL COMPARISON"
        )

        print(
            "=" * 60
        )

        print(
            results_df.to_string(
                index=False
            )
        )

        # --------------------------------------
        # SAVE OPTIMIZED XGBOOST
        # --------------------------------------

        joblib.dump(
            tuned_xgb,
            self.model_path
        )

        # Save threshold separately
        joblib.dump(
            best_threshold,
            os.path.join(
                "models",
                "best_threshold.pkl"
            )
        )

        # Save results
        results_df.to_csv(
            self.results_path,
            index=False
        )

        # Detailed evaluation
        self.save_classification_report(
            tuned_xgb,
            X_test,
            y_test,
            best_threshold
        )

        self.save_confusion_matrix(
            tuned_xgb,
            X_test,
            y_test,
            best_threshold
        )

        self.save_model_comparison(
            results_df
        )

        print(
            "\nOptimized XGBoost saved successfully!"
        )

        print(
            f"Best Threshold: "
            f"{best_threshold:.2f}"
        )

        return (
            tuned_xgb,
            results_df,
            best_threshold
        )


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    print(
        "\nStarting Data Transformation..."
    )

    data_transformation = DataTransformation()

    (
        X_train,
        X_test,
        y_train,
        y_test,
        preprocessor
    ) = (
        data_transformation
        .initiate_data_transformation()
    )

    model_trainer = ModelTrainer()

    (
        best_model,
        results,
        best_threshold
    ) = (
        model_trainer
        .initiate_model_training(
            X_train,
            X_test,
            y_train,
            y_test
        )
    )

    print(
        "\nTRAINING COMPLETED SUCCESSFULLY!"
    )