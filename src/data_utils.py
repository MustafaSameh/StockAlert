import pandas as pd
import numpy as np
from sqlalchemy import create_engine, inspect

def manual_rop_calculator(  current_stock: int  
                          , avg_sales:float 
                          , std_dev_sales: float 
                          , lead_time: int):

    
    # Calculate the Reorder Point (ROP) using the formula:
    safety_stock = 1.65 * std_dev_sales * np.sqrt(lead_time)
    rop = (avg_sales * lead_time) + safety_stock

    # Check if the current stock is below or above the ROP
    if current_stock <= rop:
        return (f"⚠️  REORDER ALERT \nCurrent stock: {current_stock} units\nReorder point : {rop:.1f} units\n→ Place a new order now")
    else:
        buffer = current_stock - rop
        return f"✅ Stock is OK\nCurrent stock: {current_stock} units\nReorder point: {rop:.1f} units\n→ {buffer:.1f} units above reorder point"

# Find the needed column in the dataframe based on user input, ignoring case and underscores
def find_column(df, user_input):

    # Normalize both the dataframe columns and user input for comparison
    matched = [col for col in df.columns if col.lower().replace('_', ' ').strip() == user_input.lower().replace('_', ' ').strip()]
    if matched:
        return matched[0]   # returns the real column name as it exists in the df
    raise ValueError(f"Column '{user_input}' not found. Available: {list(df.columns)}")

# Find date column in the dataframe based on most common date-related column names, ignoring case and underscores
def find_date_column(df):
    synonyms = ['date', 'datetime', 'timestamp', 'time', 'day', 'period']
    for col in df.columns:
        col_lower = col.lower().strip()
        if col_lower in synonyms or any(s in col_lower for s in synonyms):
            return col
    return None

# SQL connection function that fethches the targeted sales data based on the product name and product column provided by the user    
def sql_connection(db_type: str, Host: str, Port: str, Username: str, Password: str, Database_name: str, sales_table: str, product_column: str, product_name: str):
    # Define the database drivers for different database types
    drivers = {
        "mysql":      "mysql+pymysql",
        "postgresql": "postgresql+psycopg2",
        "sqlite":     "sqlite",
    }
    driver  = drivers.get(db_type, db_type)
    
    engine = create_engine(
        f"{driver}://{Username}:{Password}@{Host}:{Port}/{Database_name}"
    )
    
    inspector = inspect(engine)
    # Replaced dataconfig['Sales_table'] with sales_table
    columns   = [col['name'] for col in inspector.get_columns(sales_table)]
    
    # Replaced dataconfig['product_column'] with product_column
    if product_column not in columns:
        raise ValueError(f"Column '{product_column}' not found. Choose from: {columns}")
    
    # Replaced dataconfig elements in the query
    quote = '"' if db_type in ['postgresql', 'sqlite'] else '`'
    if product_name:
        query = f"SELECT * FROM {quote}{sales_table}{quote} WHERE {quote}{product_column}{quote} = '{product_name}'"    
    else:
        query = f"SELECT * FROM {quote}{sales_table}{quote}"    
    
    targeted_sales = pd.read_sql(query, engine)
    return targeted_sales

# Data Sanitizer is our Dettol for the dataset. It cleans duplicates, nulls, and outliers in the sales data. 
def data_sanitizer(targeted_sales, sales_column):
    
    # Nested functions to handle duplicates, outliers, and nulls in the dataset

    # Drop duplicates if any exist
    def duplicates_sanitizer(targeted_sales):
        if targeted_sales.duplicated().sum() != 0:  
           # FIX: Changed 'df' to 'targeted_sales' to resolve NameError namespace issue
           targeted_sales = targeted_sales.drop_duplicates().copy()
        return targeted_sales
    
    # Handle outliers using the IQR method
    def outliers_sanitizer(ts_df):
        col_data = pd.to_numeric(ts_df[sales_column], errors='coerce')
        q1 = pd.Series(sorted(ts_df[sales_column])).quantile(0.25)
        q3 = pd.Series(sorted(ts_df[sales_column])).quantile(0.75)
        IQR = q3 - q1
        upper_fence = q3 + 1.5 * IQR
        lower_fence = max(0, q1 - 1.5 * IQR)
        # FIX: Working safely and directly on the scoped variable mapping
        ts_df[sales_column] = ts_df[sales_column].clip(lower_fence, upper_fence)
        return ts_df
    
    # Hnandle null values by filling them with the mean of the sales column that we got after handling outliers
    def nulls_sanitizer(targeted_sales):   
        if targeted_sales[sales_column].isna().sum() != 0: 
            targeted_sales[sales_column] = targeted_sales[sales_column].fillna(targeted_sales[sales_column].mean())       
        return targeted_sales

    targeted_sales = duplicates_sanitizer(targeted_sales)
    targeted_sales = nulls_sanitizer(targeted_sales)
    targeted_sales = outliers_sanitizer(targeted_sales)
    return targeted_sales