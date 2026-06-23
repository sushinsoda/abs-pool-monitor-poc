# Databricks notebook source
bronze = spark.table("workspace.abs.bronze_loan_tape")
bronze.printSchema()

# COMMAND ----------

from pyspark.sql.functions import col

silver = (bronze.withColumn("original_balance_eur", col("original_balance_eur").cast("double"))
          .withColumn("current_balance_eur", col("current_balance_eur").cast("double"))
          .withColumn("interest_rate_pct", col("interest_rate_pct").cast("double"))
)

silver.printSchema()

# COMMAND ----------

silver = (silver
    .withColumn("term_months",    col("term_months").cast("int"))
    .withColumn("months_on_book", col("months_on_book").cast("int"))
)

silver.printSchema()

# COMMAND ----------

from pyspark.sql.functions import to_date

silver = (silver
    .withColumn("reporting_date", to_date(col("reporting_date"), "yyyy-MM-dd"))
    .withColumn("origination_date", to_date(col("origination_date"), "dd/MM/yyyy"))
)
silver.printSchema()

# COMMAND ----------

silver.select("reporting_date", "origination_date").show(5)

# COMMAND ----------

silver

# COMMAND ----------

silver.groupBy("arrears_status").count().show()

# COMMAND ----------

from pyspark.sql.functions import count, upper, trim, col

silver = silver.withColumn("arrears_status", upper(trim(col("arrears_status"))))
silver.groupBy("arrears_status").count().show()
silver.groupBy("country").count().show()
silver.groupBy("product").count().show()

# COMMAND ----------

silver

# COMMAND ----------

total = silver.count()
distinct = silver.distinct().count()

print("Total rows:   ", total)
print("Distinct rows:", distinct)
print("Duplicates:   ", total - distinct)

# COMMAND ----------

silver = silver.dropDuplicates()

print("Rows after dedupe:", silver.count())

# COMMAND ----------

from pyspark.sql.functions import count, when 

silver.select(count(when(col("current_balance_eur").isNull(),1)).alias("nulls"),
              count(when(col("current_balance_eur") < 00,1)).alias("negatives")).show()


# COMMAND ----------

silver.filter(col("current_balance_eur") < 0).select(
    "loan_id", "reporting_date", "original_balance_eur", "current_balance_eur"
).show()

# COMMAND ----------

silver = silver.withColumn(
    "current_balance_eur",
    when(col("current_balance_eur") < 0, None).otherwise(col("current_balance_eur"))
)

# COMMAND ----------

silver.select(
    count(when(col("current_balance_eur").isNull(), 1)).alias("nulls"),
    count(when(col("current_balance_eur") < 0, 1)).alias("negatives")
).show()


# COMMAND ----------

from pyspark.sql.functions import col

bad = silver.filter(col("current_balance_eur").isNull())
quarantine = bad.filter(~col("arrears_status").isin("PAID OFF", "CHARGED OFF"))

(quarantine.write.format("delta").mode("overwrite")
    .saveAsTable("workspace.abs.silver_quarantine"))

print("All nulls:        ", bad.count())
print("Active + null:    ", quarantine.count())


# COMMAND ----------

from pyspark.sql.functions import when, col, lit

silver = silver. withColumn("dq_flag", when(col("current_balance_eur").isNull() &
                                           ~col("arrears_status").isin("PAID OFF", "CHARGED OFF"),
                                           lit("active_null_balance")).otherwise(lit(None)))

# COMMAND ----------

silver.groupBy("dq_flag").count().show()

# COMMAND ----------

(silver.write.format("delta").mode("overwrite")
    .saveAsTable("workspace.abs.silver_loan_tape"))

print("Silver rows:", spark.table("workspace.abs.silver_loan_tape").count())