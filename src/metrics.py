"""Metrics shared by training and evaluation. Inputs are log(price)."""
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error


def regression_metrics(y_log, pred_log):
    y_log, pred_log = np.asarray(y_log), np.asarray(pred_log)
    price, pred = np.exp(y_log), np.exp(pred_log)
    ape = np.abs(pred - price) / price
    return {
        "mape": float(ape.mean()),               # mean absolute % error
        "median_ape": float(np.median(ape)),     # typical % error
        "within_10": float((ape <= 0.10).mean()),
        "within_20": float((ape <= 0.20).mean()),
        "rmse_log": float(root_mean_squared_error(y_log, pred_log)),
        "r2_log": float(r2_score(y_log, pred_log)),
        "r2_inr": float(r2_score(price, pred)),
        "mae_lakh": float(mean_absolute_error(price, pred) / 1e5),
    }
