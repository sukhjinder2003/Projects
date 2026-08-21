import os
import pandas as pd


class DataIngestion:

    def __init__(self):
        self.raw_data_path = os.path.join(
            "data",
            "raw",
            "WA_Fn-UseC_-HR-Employee-Attrition.csv"
        )

        self.processed_data_path = os.path.join(
            "data",
            "processed",
            "employee_data.csv"
        )

    def initiate_data_ingestion(self):

        try:
            print("Data ingestion started...")

            # Load dataset
            df = pd.read_csv(self.raw_data_path)

            print("Dataset loaded successfully.")
            print(f"Dataset shape: {df.shape}")

            # Create processed directory if needed
            os.makedirs(
                os.path.dirname(self.processed_data_path),
                exist_ok=True
            )

            # Save dataset
            df.to_csv(
                self.processed_data_path,
                index=False
            )

            print("Data ingestion completed successfully.")

            return self.processed_data_path

        except Exception as e:
            print(f"Error occurred: {e}")
            raise e


if __name__ == "__main__":

    data_ingestion = DataIngestion()

    data_path = data_ingestion.initiate_data_ingestion()

    print(f"Processed data saved at: {data_path}")