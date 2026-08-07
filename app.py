# Import Required Libraries 
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine, inspect
from datetime import datetime
from pathlib import Path
from prophet import Prophet
import pandas as pd
import numpy as np
import streamlit as st 

#-----------------------
# Backend #
#-----------------------

# Manual ROP Calculator Function (If you know your numbers quite well, you can just enter them and get the ROP)
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
    query = f"SELECT * FROM {quote}{sales_table}{quote} WHERE {quote}{product_column}{quote} = '{product_name}'"    
    
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
        q1 = pd.Series(sorted(ts_df[sales_column])).quantile(0.25)
        q3 = pd.Series(sorted(ts_df[sales_column])).quantile(0.75)
        IQR = q3 - q1
        upper_fence = q3 + 1.5 * IQR
        lower_fence = max(0, q1 - 1.5 * IQR)
        # FIX: Working safely and directly on the scoped variable mapping
        ts_df.loc[:, sales_column] = ts_df[sales_column].clip(lower_fence, upper_fence)
        return ts_df
    
    # Hnandle null values by filling them with the mean of the sales column that we got after handling outliers
    def nulls_sanitizer(targeted_sales):   
        if targeted_sales[sales_column].isna().sum() != 0: 
            targeted_sales.loc[:, sales_column] = targeted_sales[sales_column].fillna(targeted_sales[sales_column].mean())       
        return targeted_sales

    targeted_sales = duplicates_sanitizer(targeted_sales)
    targeted_sales = nulls_sanitizer(targeted_sales)
    targeted_sales = outliers_sanitizer(targeted_sales)
    return targeted_sales

# StockAlert class encapsulates the logic for calculating ROP, checking stock levels, and scheduling automated checks.
class StockAlert:
    # Initialize the class with the required parameters
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
        self.targeted_sales = data_sanitizer(
            self.targeted_sales, 
            self.sales_column
    )
    def calculate_rop(self):
        avg = self.targeted_sales[self.sales_column].mean()
        std = self.targeted_sales[self.sales_column].std()

        if pd.isna(std):
            std = 0.0
            
        safety_stock = 1.65 * std * np.sqrt(self.lead_time)        
        self.rop = (avg * self.lead_time) + safety_stock
        self.avg_sales = avg
        self.std_dev = std
        
        return self.rop, self.avg_sales, self.std_dev

    def calculate_days_of_stock(self, order_quantity: int) -> str:
        """Returns how many days a specific order quantity will last."""
        days = (order_quantity - self.rop) / self.avg_sales if self.avg_sales != 0 else 0
        return f"→ {order_quantity} units will last approximately {days:.1f} days."

    def calculate_quantity_for_days(self, target_days: int) -> str:
        """Returns the recommended order quantity to last a specific number of days."""
        qty = self.rop + (self.avg_sales * target_days)
        return f"→ Recommended order quantity for {target_days} days: {qty:.1f} units."

    def check_stock(self , current_stock: float):
        if current_stock <= self.rop:
            return f"⚠️ REORDER ALERT: Current stock ({current_stock}) is at or below ROP ({self.rop:.1f})"
        else:
            buffer = current_stock - self.rop
            return f"✅ Stock OK: {buffer:.1f} units above ROP ({self.rop:.1f})"

    def daily_stock_check(self):
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 🔄 Daily stock check...")
        
        if self.inventory_column is None:
                print("  ℹ️  No inventory column configured — skipping automated check")
                return
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


#-----------------------
# Frontend #
#-----------------------        
def main ():
   
    st.set_page_config(page_title="StockAlert ROP Calculator", layout="wide")
    st.title("📦 StockAlert Inventory Manager")

    # 1. Top Level Choice (Maps to your first flowchart box)
    tab_manual, tab_auto, tab_order , tab_forcasting = st.tabs(["🧮 Manual ROP", "🤖 Automatic Calculation", "📦 Order Quantity Planner", "📊 Seasonal Forecasting"])

    # ==========================================
    # TAB 1: MANUAL CALCULATOR
    # ==========================================
    with tab_manual:
        st.header("Manual ROP Calculator")
        st.write("Just enter your numbers and we will calculate the ROP.")
        
        # Recreating your 2x2 grid using Streamlit columns
        col1, col2 = st.columns(2)
        with col1:
            current_stock = st.number_input("Current Stock:", min_value=0, step=1)
            std_dev = st.number_input("Standard Deviation of Sales:", min_value=0.0)
        with col2:
            avg_sales = st.number_input("Average Sales:", min_value=0.0)
            lead_time = st.number_input("Lead Time (Days):", min_value=0, step=1)
            
        if st.button("Calculate Manual ROP"):
            result_text = manual_rop_calculator(current_stock, avg_sales, std_dev, lead_time)
            # 3. We tell Streamlit to display that exact text on the screen!
            st.info(result_text)

    # ==========================================
    # TAB 2: AUTOMATIC CALCULATION
    # ==========================================
    with tab_auto:
        st.header("Automatic ROP Calculation")
        
        # Sub-branch: Database vs Upload
        data_source = st.radio("Choose your data source:", ["Upload Dataset (CSV)", "Connect to Database"])
        
        if data_source == "Upload Dataset (CSV)":
            st.subheader("Upload your CSV file")
            uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
            
            if uploaded_file is not None:
                # Display the dataframe as you designed in the wireframe
                df = pd.read_csv(uploaded_file) 
                st.dataframe(df.head()) 
                st.write("### Please fill these fields:")
                col_a, col_b = st.columns(2)
                with col_a:
                    product_name = st.text_input("Product Name:") 
                    
                    
                    review_period = st.number_input("Review Period (Days):", value=90)
                with col_b:
                    sales_column = st.text_input("Sales Column Name (e.g., Units Sold):")
                    
                    product_column = st.text_input("Product Column Name:")
                    lead_time_auto = st.number_input("Lead Time:", min_value=0)

                st.session_state['saved_sales_col'] = sales_column
                st.session_state['saved_leadtime'] = lead_time_auto
                st.session_state['saved_product_name'] = product_name
                # Sub-branch for stock level choice 
                stock_choice = st.radio("How to check current stock?", ["Manual Stock Level", "From Column"])
                if stock_choice == "Manual Stock Level":
                    manual_stock = st.number_input("Enter current stock:")
                else:
                    stock_column = st.text_input("Enter stock column name:")
                    
                if st.button("Run Automatic Analysis"):
                    # TODO: Initialize StockAlert class and run logic here!
                    targeted = df[df[product_column] == product_name].copy()
                    alert = StockAlert(targeted_sales=targeted, sales_column=sales_column, lead_time=lead_time_auto)
                    st.session_state['my_saved_df'] = targeted
                    alert.clean()
                    calculated_rop, calculated_avg, calculated_std = alert.calculate_rop()
                    if stock_choice == "Manual Stock Level":
                        current_stock = manual_stock
                    else:
                        # Grab the very last row of the dataset and look at the stock column
                        current_stock = df.iloc[-1][stock_column]
                        
                    # 4. Check the stock status
                    result_text = alert.check_stock(current_stock)
                    
                    # 5. Display the final results beautifully on the screen!
                    st.write(f"**Calculated ROP:** {calculated_rop:.1f} units")
                    st.write(f"**(Avg Sales:** {calculated_avg:.1f} | **Std Dev:** {calculated_std:.1f})")
                    st.info(result_text)
                    st.success("Backend automated analysis will appear here.")
                    
        elif data_source == "Connect to Database":
            st.subheader("Connect to your Database")
            
            db_col1, db_col2 = st.columns(2)
            with db_col1:
                db_type = st.selectbox("Database Type:", ["mysql", "postgresql", "sqlite"])
                db_port = st.text_input("Port (e.g., 3306 or 5432):")
                db_pass = st.text_input("Password:", type="password")
                # NEW: Missing dataconfig inputs
                sales_table = st.text_input("Sales Table Name:")
                product_name = st.text_input("Product Name:")
            with db_col2:
                db_host = st.text_input("Host (e.g., localhost):")
                db_user = st.text_input("Username:")
                db_name = st.text_input("Database Name:")
                # NEW: Missing dataconfig inputs
                product_column = st.text_input("Product Column Name:")
                sales_column = st.text_input("Sales Column Name (e.g., Units Sold):")
                lead_time_db = st.number_input("Lead Time (Days):", min_value=0)
                
            inventory_col_db = st.text_input("Inventory Column Name (for current stock):")

            if st.button("Connect & Analyze"):
                try:
                    df = sql_connection(db_type, db_host, db_port, db_user, db_pass, db_name, sales_table, product_column, product_name)
                    targeted = df[df[product_column] == product_name].copy()
                    st.session_state['my_saved_df'] = targeted
                    st.session_state['saved_product_name'] = product_name
                    st.session_state['saved_leadtime'] = lead_time_db 
                    st.session_state['saved_sales_col'] = sales_column
                    alert = StockAlert(targeted_sales=targeted, sales_column=sales_column, lead_time=lead_time_db)
                    alert.clean()
                    calculated_rop, calculated_avg, calculated_std = alert.calculate_rop()
                    
                    # Get current stock from inventory column
                    date_col = find_date_column(df)
                    latest_row = df.sort_values(date_col).iloc[-1] if date_col else df.iloc[-1]
                    current_stock = latest_row[inventory_col_db]
                    
                    result_text = alert.check_stock(current_stock)
                    st.write(f"**Calculated ROP:** {calculated_rop:.1f} units")
                    st.info(result_text)
                except Exception as e:
                    st.error(f"Error: {e}")
    # ==========================================
    # TAB 3: ORDER QUANTITY PLANNER
    # ==========================================
    with tab_order:
        st.header("Order Quantity Planning")
        st.write("Plan your next purchase based on your calculated ROP and Average Sales.")

        # Ask the user for the variables needed for the math
        col_x, col_y = st.columns(2)
        with col_x:
            known_rop = st.number_input("Enter your calculated ROP:", min_value=0.0)
        with col_y:
            known_avg_sales = st.number_input("Enter your Average Daily Sales:", min_value=0.0)

        st.divider() # Adds a nice horizontal line for visual separation

        # Replaces your terminal choice input ("1 for yes, 2 for no")
        calc_choice = st.radio(
            "What would you like to calculate?", 
            ["Days of Stock (I know the quantity I want to buy)", "Order Quantity (I know how many days I want to cover)"]
        )

        # Choice 1 Logic
        if calc_choice == "Days of Stock (I know the quantity I want to buy)":
            qty = st.number_input("Enter the desired order quantity (units):", min_value=0, step=1)
            
            if st.button("Calculate Days"):
                if known_avg_sales > 0:
                    days = (qty - known_rop) / known_avg_sales
                    st.success(f"📦 {qty} units will last approximately **{days:.1f} days**.")
                else:
                    st.warning("Average sales must be greater than 0 to calculate days.")
                    
        # Choice 2 Logic
        else:
            days = st.number_input("Enter the desired stock duration (days):", min_value=0, step=1)
            
            if st.button("Calculate Quantity"):
                qty = known_rop + (known_avg_sales * days)
                st.success(f"🛒 Recommended order quantity for {days} days: **{qty:.1f} units**.")

    # ==========================================
    # TAB 4: SEASONAL FORECASTING
    # ==========================================
    with tab_forcasting:
        st.header("Seasonal Forecasting")
        st.write("Forecast future sales using Prophet with holiday effects.")
        
        # 1. The User UI: Let the user select their custom date range
        st.write("Select the specific period you want to calculate ROP for:")
        col_start, col_end = st.columns(2)
        with col_start:
            start_date = st.date_input("Start Date")
            country = st.text_input("Enter the country code for holidays (e.g., 'EG' for Egypt, 'US' for USA):")
        with col_end:
            end_date = st.date_input("End Date")

        if st.button("Calculate Seasonal ROP"):
            # 3. The Filter: Slice the forecast dataframe to match the user's dates
            
            if 'my_saved_df' in st.session_state and 'saved_sales_col' in st.session_state and 'saved_leadtime' in st.session_state and 'saved_product_name' in st.session_state:
                # Retrieve data without asking the user again for inputs.
                forecast_df = st.session_state['my_saved_df']
                sales_col = st.session_state['saved_sales_col']
                lead_time = st.session_state['saved_leadtime']
                product_name = st.session_state['saved_product_name']
                st.success("Successfully loaded your data from the previous tab!")

                m = Prophet() 
                m.add_country_holidays(country_name=country) # 'EG' for Egypt, 'US' for USA, 'DE' for Germany, etc.
                prophet_df = forecast_df.rename(columns={find_date_column(forecast_df): 'ds', sales_col: 'y'})
                m.fit(prophet_df)
                future = m.make_future_dataframe(periods=1825)  
                forecast = m.predict(future)

                mask = (forecast['ds'] >= pd.to_datetime(start_date)) & (forecast['ds'] <= pd.to_datetime(end_date))
                specific_period_data = forecast.loc[mask]

                if not specific_period_data.empty:
                    # 4. The Math: Apply your ROP equation to just those dates!
                    seasonal_alert = StockAlert(
                            targeted_sales=specific_period_data,
                            sales_column='yhat',
                            lead_time=lead_time
                        )
                        
                        # Now call the exact same function. It works perfectly!
                    seasonal_rop, seasonal_avg, seasonal_std = seasonal_alert.calculate_rop()
                        
                        # Display the final results beautifully
                    st.divider()
    
                    # 3. Display the Trend Line Chart
                    st.write("### 📈 Forecasted Sales Trend")
                    # Format dataframe for Streamlit chart index
                    chart_data = (
                        specific_period_data[['ds', 'yhat']]
                        .rename(columns={'ds': 'Date', 'yhat': 'Forecasted Sales'})
                        .set_index('Date')
                    )
                    st.line_chart(chart_data)
    
                    # 4. Display the Filtered DataFrame Table
                    st.write(f"### 📋 Daily Forecast Breakdown for {product_name} from {start_date} to {end_date} ")
                    st.dataframe(
                        specific_period_data[['ds', 'yhat']]
                        .rename(columns={'ds': 'Date', 'yhat': 'Forecasted Sales'})
                        .reset_index(drop=True),
                        use_container_width=True
                    )
    
                    st.subheader("🎯 Projected Seasonal ROP")
                    st.write(f"**Recommended Reorder Point:** {seasonal_rop:.1f} units")
                    st.write(f"*(Forecasted Avg Daily Sales: {seasonal_avg:.1f} | Forecasted Std Dev: {seasonal_std:.1f})*")
                    
                else:
                    st.warning("No forecast data available for the selected dates. Try a different range.")
                
            else:
                st.warning("Please go to the Auto tab and upload your data first.")

                                
        else:
            st.warning("Please go to the Auto tab and run the Automatic Analysis first so we can load your data.")
                                    
main()