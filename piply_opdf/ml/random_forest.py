import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

import sqlite3

def get_database_connection():
    conn = sqlite3.connect('piply_opdf_knowledge-001.db')
    return conn

def query_database(query):
    conn = get_database_connection()
    cursor = conn.cursor()
    cursor.execute(query)
    results = cursor.fetchall()
    conn.close()
    return results

# Example usage in random_forest.py

def fetch_knowledge_data():
    query = "SELECT * FROM knowledge_table"
    results = query_database(query)
    return results

def load_data_from_db():
    """Load data from the database."""
    data = fetch_knowledge_data()
    df = pd.DataFrame(data, columns=['feature1', 'feature2', 'target'])
    return df

# Example usage
if __name__ == "__main__":
    data = load_data_from_db()
    X_train, X_test, y_train, y_test = split_data(data)
    model = train_random_forest(X_train, y_train)
    accuracy = evaluate_model(model, X_test, y_test)
    print(f"Model Accuracy: {accuracy:.2f}")