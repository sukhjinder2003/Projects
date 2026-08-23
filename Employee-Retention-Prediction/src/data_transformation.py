import pandas as pd
import os
import joblib

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer


class DataTransformation:
    def __init__(self):

        self.processed_data_path = os.path.join(
            "data", "processed", "employee_data.csv"
        )

        self.preprocessor_path = os.path.join("models", "preprocessor.pkl")

    def initiate_data_transformation(self):

        try:
            print("Data transformation started...")

            # ==========================================
            # LOAD DATASET
            # ==========================================

            df = pd.read_csv(self.processed_data_path)

            # ==========================================
            # CLEAN COLUMN NAMES
            # ==========================================

            # Remove extra spaces from column names
            df.columns = df.columns.str.strip()

            # Fix incorrect Age column name
            df.rename(
                columns={"dir data\\rawAge": "Age", "dir data/rawAge": "Age"},
                inplace=True,
            )

            print("\nDataset Columns:")
            print(df.columns.tolist())

            print(f"\nOriginal dataset shape: {df.shape}")

            # ==========================================
            # REMOVE DUPLICATES
            # ==========================================

            df.drop_duplicates(inplace=True)

            print(f"Dataset shape after removing duplicates: {df.shape}")

            # ==========================================
            # DROP UNNECESSARY COLUMNS
            # ==========================================

            columns_to_drop = [
                "EmployeeCount",
                "EmployeeNumber",
                "Over18",
                "StandardHours",
            ]

            df.drop(columns=columns_to_drop, inplace=True, errors="ignore")

            print(f"\nDataset shape after dropping unnecessary columns: {df.shape}")

            # ==========================================
            # SEPARATE FEATURES AND TARGET
            # ==========================================

            X = df.drop("Attrition", axis=1)

            y = df["Attrition"].map({"Yes": 1, "No": 0})

            # Check if target conversion worked
            if y.isnull().sum() > 0:
                raise ValueError("Unexpected values found in Attrition column.")

            # ==========================================
            # IDENTIFY NUMERICAL AND CATEGORICAL FEATURES
            # ==========================================

            numerical_features = X.select_dtypes(
                include=["int64", "float64"]
            ).columns.tolist()

            categorical_features = X.select_dtypes(include=["object"]).columns.tolist()

            print(f"\nNumber of numerical features: {len(numerical_features)}")

            print(f"Number of categorical features: {len(categorical_features)}")

            print("\nNumerical Features:")

            print(numerical_features)

            print("\nCategorical Features:")

            print(categorical_features)

            # ==========================================
            # NUMERICAL PIPELINE
            # ==========================================

            numerical_pipeline = Pipeline(
                steps=[
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", StandardScaler()),
                ]
            )

            # ==========================================
            # CATEGORICAL PIPELINE
            # ==========================================

            categorical_pipeline = Pipeline(
                steps=[
                    ("imputer", SimpleImputer(strategy="most_frequent")),
                    ("encoder", OneHotEncoder(handle_unknown="ignore")),
                ]
            )

            # ==========================================
            # COMBINE PREPROCESSING
            # ==========================================

            preprocessor = ColumnTransformer(
                transformers=[
                    ("num", numerical_pipeline, numerical_features),
                    ("cat", categorical_pipeline, categorical_features),
                ]
            )

            # ==========================================
            # TRAIN-TEST SPLIT
            # ==========================================

            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.20, random_state=42, stratify=y
            )

            print(f"\nTraining data shape: {X_train.shape}")

            print(f"Testing data shape: {X_test.shape}")

            # ==========================================
            # FIT PREPROCESSOR
            # ==========================================

            X_train_transformed = preprocessor.fit_transform(X_train)

            X_test_transformed = preprocessor.transform(X_test)

            # ==========================================
            # CREATE MODELS DIRECTORY
            # ==========================================

            os.makedirs("models", exist_ok=True)

            # ==========================================
            # SAVE PREPROCESSOR
            # ==========================================

            joblib.dump(preprocessor, self.preprocessor_path)

            print("\nPreprocessor saved successfully.")

            print("Data transformation completed successfully.")

            # ==========================================
            # RETURN TRANSFORMED DATA
            # ==========================================

            return (
                X_train_transformed,
                X_test_transformed,
                y_train,
                y_test,
                preprocessor,
            )

        except Exception as e:
            print(f"\nError occurred: {e}")

            raise e


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":
    data_transformation = DataTransformation()

    (X_train, X_test, y_train, y_test, preprocessor) = (
        data_transformation.initiate_data_transformation()
    )

    print("\n" + "=" * 50)

    print("FINAL TRANSFORMED SHAPES")

    print("=" * 50)

    print(f"X_train: {X_train.shape}")

    print(f"X_test: {X_test.shape}")

    print(f"y_train: {y_train.shape}")

    print(f"y_test: {y_test.shape}")
