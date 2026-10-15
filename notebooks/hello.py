# Databricks notebook source
# Placeholder used by resources/jobs.yml. Delete when the first real job exists.
dbutils.widgets.text("catalog", "workspace")
print(f"Bundle deployed. Catalog: {dbutils.widgets.get('catalog')}")
