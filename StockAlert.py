# Import Required Libraries 
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine, inspect
from datetime import datetime
from pathlib import Path
import tkinter as tk
from   tkinter import filedialog
import pandas as pd
import numpy as np

data = None
# Functions_Part

def user_choice():
    print("\nHow would you like to calculate your ROP and check stock levels?")
    print("  1. Read from dataset and SQL database")
    print("  2. ROP calculator(Manual)")
    choice = input("\nEnter 1 or 2: ").strip()
    return choice

def manual_rop_calculator():
    config = {
        "current_stock" : int(input("Enter current stock level: ")),
        "avg_sales" : int(input("Enter average sales per day: ")),
        "std_dev_sales" : int(input("Enter standard deviation of sales per day: ")),
        "lead_time" : int(input("Enter lead time in days: ")),
    }
    # FIX: Removed trailing comma that accidentally cast safety_stock into a tuple
    config["safety_stock"] = 1.65 * config["std_dev_sales"] * np.sqrt(config["lead_time"])
    config["rop"] = (config["avg_sales"] * config["lead_time"]) + config["safety_stock"]
    
    if config["current_stock"] <= config["rop"]:
        print(f"⚠️  REORDER ALERT")
        print(f"    Current stock : {config['current_stock']} units")
        print(f"    Reorder point : {config['rop']:.1f} units")
        print(f"    → Place a new order now")
    else:
        buffer = config["current_stock"] - config["rop"]
        print(f"✅  Stock is OK")
        print(f"    Current stock : {config['current_stock']} units")
        print(f"    Reorder point : {config['rop']:.1f} units")
        print(f"    → {buffer:.1f} units above reorder point")

def load_csv_file():
    """Dynamically loads a dataset via OS file dialog or terminal path input."""
    print("\n📂 Choose dataset source:")
    print("  1. Open Desktop File Picker (Browse files)")
    print("  2. Enter file path or Drag & Drop file here")
    choice = input("Enter 1 or 2: ").strip()

    file_path = None

    if choice == "1":
        # Hidden root window so only the file dialogue pops up
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)  # Brings popup window to front
        
        file_path = filedialog.askopenfilename(
            title="Select Sales Dataset",
            filetypes=[("CSV Files", "*.csv"), ("Excel Files", "*.xlsx *.xls"), ("All Files", "*.*")]
        )
        root.destroy()

    # Fallback to manual entry/drag-and-drop if choice 2 or dialog canceled
    if not file_path:
        raw_input = input("\nEnter file path (or drag & drop file here): ").strip("'\" ")
        file_path = raw_input

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"❌ File not found at path: {path}")

    print(f"✅ Successfully loaded dataset: {path.name}")
    
    # Reads either CSV or Excel seamlessly
    if path.suffix.lower() in ['.xlsx', '.xls']:
        return pd.read_excel(path)
    return pd.read_csv(path)

def find_column(df, user_input):
    # ENHANCEMENT: Also handles underscores (.replace('_', ' ')) so typing 'inventory_level' matches 'Inventory Level'
    matched = [col for col in df.columns if col.lower().replace('_', ' ').strip() == user_input.lower().replace('_', ' ').strip()]
    if matched:
        return matched[0]   # returns the real column name as it exists in the df
    raise ValueError(f"Column '{user_input}' not found. Available: {list(df.columns)}")

def find_date_column(df):
    synonyms = ['date', 'datetime', 'timestamp', 'time', 'day', 'period']
    for col in df.columns:
        col_lower = col.lower().strip()
        if col_lower in synonyms or any(s in col_lower for s in synonyms):
            return col
    return None

def get_product(data):
    config = {
        "product_column": find_column(data, input("Enter product column name: ")),
        "product_name":   input("Enter the product name: ").strip(),
        "sales_column":   find_column(data, input("Enter sales column name: ")),
        "lead_time":      int(input("Lead time (days): ")),
        "restock_days":   int(input("How many days between restocks (e.g. 30, 0 if unknown): ")),
        "review_period":  int(input("Recalculate ROP every how many days? (90 recommended): ")),
    }
    config["targeted_sales"] = data.loc[
        data[config["product_column"]] == config["product_name"]
    ].copy()
    
    return (
        config["targeted_sales"],
        config["sales_column"],
        config["lead_time"],
        config["restock_days"],
        config["review_period"],
    )

def get_db_data():
    dataconfig = {
        "Sales_table":  input("Enter sales table name: ").strip(),
        "sales_column": input("Enter sales column name: ").strip(),
        "lead_time":    int(input("Lead time (days): ")),
        "restock_days": int(input("How many days between restocks (e.g. 30, 0 if unknown): ")),
        "review_period":int(input("Recalculate ROP every how many days? (90 recommended): ")),
    }
    return dataconfig

def sql_connection(dataconfig):
    dbconfig = {
        "db_type":       input("Enter database type (mysql / postgresql / sqlite): ").strip().lower(),
        "Host":          input("Localhost or IP address: ").strip(),
        "Port":          input("Port (3306 for MySQL, 5432 for PostgreSQL): ").strip(),
        "Username":      input("Database username: ").strip(),
        "Password":      input("Database password: ").strip(),
        "Database_name": input("Database name: ").strip(),
    }
 
    drivers = {
        "mysql":      "mysql+pymysql",
        "postgresql": "postgresql+psycopg2",
        "sqlite":     "sqlite",
    }
    db_type = dbconfig["db_type"]
    driver  = drivers.get(db_type, db_type)
 
    engine = create_engine(
        f"{driver}://{dbconfig['Username']}:{dbconfig['Password']}"
        f"@{dbconfig['Host']}:{dbconfig['Port']}/{dbconfig['Database_name']}"
    )
 
    # Show real column names from the database before asking user to type them
    inspector = inspect(engine)
    columns   = [col['name'] for col in inspector.get_columns(dataconfig['Sales_table'])]
    print(f"\n  Available columns: {columns}")
 
    # Ask for product column AFTER user sees the list
    dataconfig['product_column'] = input("\n  Enter exact product column name: ").strip()
    if dataconfig['product_column'] not in columns:
        raise ValueError(
            f"Column '{dataconfig['product_column']}' not found. Choose from: {columns}"
        )
 
    # Ask for product name AFTER validation passes
    dataconfig['product_name'] = input("  Enter product name: ").strip()
 
    # Query the database
    # FIX: Uses double quotes for cross-database identifier compatibility (MySQL/Postgres/SQLite)
    quote = '"' if dbconfig['db_type'] in ['postgresql', 'sqlite'] else '`'
    query = f"SELECT * FROM {quote}{dataconfig['Sales_table']}{quote} WHERE {quote}{dataconfig['product_column']}{quote} = '{dataconfig['product_name']}'"    
    targeted_sales = pd.read_sql(query, engine)
    return targeted_sales

def data_sentizer(targeted_sales, sales_column):
    
    def duplicates_sentizer(targeted_sales):
        if targeted_sales.duplicated().sum() != 0:  
           # FIX: Changed 'df' to 'targeted_sales' to resolve NameError namespace issue
           targeted_sales = targeted_sales.drop_duplicates().copy()
        return targeted_sales
    
    def outliers_sentizer(ts_df):
        q1 = pd.Series(sorted(ts_df[sales_column])).quantile(0.25)
        q3 = pd.Series(sorted(ts_df[sales_column])).quantile(0.75)
        IQR = q3 - q1
        upper_fence = q3 + 1.5 * IQR
        lower_fence = max(0, q1 - 1.5 * IQR)
        # FIX: Working safely and directly on the scoped variable mapping
        ts_df.loc[:, sales_column] = ts_df[sales_column].clip(lower_fence, upper_fence)
        return ts_df
    
    def nulls_sentizer(targeted_sales):   
        if targeted_sales[sales_column].isna().sum() != 0: 
            targeted_sales.loc[:, sales_column] = targeted_sales[sales_column].fillna(targeted_sales[sales_column].mean())       
        return targeted_sales

    targeted_sales = duplicates_sentizer(targeted_sales)
    targeted_sales = nulls_sentizer(targeted_sales)
    targeted_sales = outliers_sentizer(targeted_sales)
    return targeted_sales


class StockAlert:
    def __init__(self,targeted_sales,sales_column,lead_time, restock_days = 0 , inventory_column = None):
        # __init__ runs automatically when you create the object
        # it just stores the shared data so you don't pass it everywhere
        self.targeted_sales     = targeted_sales
        self.sales_column       = sales_column
        self.lead_time          = lead_time
        self.restock_days       = restock_days
        self.inventory_column   = inventory_column
        self.rop                = None   # calculated later
        self.avg_sales          = None
        self.std_dev            = None
    


    def clean(self):
    # no need to pass targeted_sales — it's already stored in self
        self.targeted_sales = data_sentizer(
        self.targeted_sales, 
        self.sales_column
    )

        def calculate_rop(self):
            avg   = self.targeted_sales[self.sales_column].mean()
            std   = self.targeted_sales[self.sales_column].std()

# Handle single row edge-case scenario where std evaluates to NaN
            if pd.isna(std):
                std = 0.0
                safety_stock = 1.65 * std * np.sqrt(self.lead_time)        
                self.rop = (avg * self.lead_time) + safety_stock
                self.avg_sales = avg
                self.std_dev = std

            return self.rop , self.avg_sales , self.std_dev

    def order_quantity(self):
        print("\nWould you like to calculate your order quantity?")
        choice = input("1 for yes, 2 for no: ").strip()
        if choice == "1":
            print("\n  1. Based on a specific quantity (units)")
            print("  2. Based on desired stock duration (days)")
            choice = input("\n  Enter 1 or 2: ").strip()
            if choice == "1":
                qty  = int(input("\n  Enter the desired order quantity: "))
                days = (qty - self.rop) / self.avg_sales if self.avg_sales != 0 else 0
                print(f"  → {qty} units will last approximately {days:.1f} days")
            else:
                days = self.restock_days
                qty  = self.rop + (self.avg_sales * days)
                print(f"  → Recommended order quantity for {days} days: {qty:.1f} units")

    def check_stock(self):
# FIX: Added optional variables to signature so it safely processes the 4 arguments passed from main()
        print("\nHow would you like to provide the current stock level?")
        print("  1. Read from dataset (if your dataset has an inventory column)")
        print("  2. Enter manually")
        choice = input("\nEnter 1 or 2: ").strip()
        if choice == "1":
            date_col = find_date_column(self.targeted_sales)
            if date_col:
                latest_row = self.targeted_sales.sort_values(date_col).iloc[-1]
            else:
                print("  ℹ️  No date column found — using last row as most recent")
                latest_row = self.targeted_sales.iloc[-1]
            self.inventory_column = find_column(self.targeted_sales, input("Enter inventory/stock column name: "))
            current_stock = latest_row[self.inventory_column]
            print(f"  → Latest inventory level from dataset: {current_stock} units")
        else:
            current_stock = int(input("Enter current stock level: "))
        
        print()
        if current_stock <= self.rop:
            print(f"⚠️  REORDER ALERT")
            print(f"    Current stock : {current_stock} units")
            print(f"    Reorder point : {self.rop:.1f} units")
            print(f"    → Place a new order now")
        else:
            buffer = current_stock - self.rop
            print(f"✅  Stock is OK")
            print(f"    Current stock : {current_stock} units")
            print(f"    Reorder point : {self.rop:.1f} units")
            print(f"    → {buffer:.1f} units above reorder point")

    def daily_stock_check(self):
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 🔄 Daily stock check...")
        
        if self.inventory_column is None:
                print("  ℹ️  No inventory column configured — skipping automated check")
                return
        current_stock = latest_row[self.inventory_column]
        try:
            date_col  = find_date_column(self.targeted_sales)
            latest_row = (
                self.targeted_sales.sort_values(date_col).iloc[-1]
                if date_col else self.targeted_sales.iloc[-1]
            )
            current_stock = latest_row[self.inventory_column]
            if current_stock <= self.rop:
                print(f"  ⚠️  REORDER ALERT")
                print(f"      Current stock : {current_stock} units")
                print(f"      Reorder point : {self.rop:.1f} units")
                print(f"      → Place a new order now")
            else:
                print(f"  ✅  Stock OK — {current_stock - self.rop:.1f} units above ROP")
        except Exception as e:
            print(f"  ❌ Daily check failed: {e}")

    def recalculate_rop(self):
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 📊 Recalculating ROP...")
        try:
            self.clean()
            new_rop, new_avg, new_std = self.calculate_rop()
            print(f"  ✅  New ROP : {new_rop:.1f} units")
            print(f"      Avg     : {new_avg:.1f} | Std dev: {new_std:.1f}")
            return new_rop
        except Exception as e:
            print(f"  ❌ Recalculation failed: {e}")


    def start_scheduler(self, review_period):
        review_weeks = max(1, review_period // 7)
        scheduler    = BackgroundScheduler()
    
        scheduler.add_job(
            self.daily_stock_check,
            trigger='cron', hour=8, id='daily_check'
        )
        scheduler.add_job(
            self.recalculate_rop,
            trigger='interval', weeks=review_weeks, id='rop_recalc'
        )
        scheduler.start()
        print(f"✅  Scheduler started")
        print(f"    Daily stock check  : every day at 8:00 AM")
        print(f"    ROP recalculation  : every {review_weeks} weeks")
        return scheduler

def main():
    choice = user_choice()
 
    if choice == "1":
        print("\nWould you like to read data from a SQL database or a CSV file?")
        source = input("Enter 1 for SQL database or 2 for CSV file: ").strip()
 
        if source == "1":
            dataconfig     = get_db_data()
            targeted_sales = sql_connection(dataconfig)
            sales_column   = dataconfig["sales_column"]
            lead_time      = dataconfig["lead_time"]
            restock_days   = dataconfig["restock_days"]
            review_period  = dataconfig["review_period"]
        else:
            data = load_csv_file()
            targeted_sales, sales_column, lead_time, restock_days, review_period = get_product(data)
 
        # Clean data and execute target logic pipeline
        alert = StockAlert(targeted_sales=targeted_sales , sales_column=sales_column , lead_time=lead_time, restock_days=restock_days)
        alert.clean()
        alert.calculate_rop()
        alert.order_quantity()
        alert.check_stock()
        alert.recalculate_rop()
        

    else:
        manual_rop_calculator()