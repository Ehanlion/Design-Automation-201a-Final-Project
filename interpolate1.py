import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

def read_data(filename):
    data = []
    with open(filename, 'r') as f:
        for line in f:
            if line.strip():
                parts = line.strip().split()
                if len(parts) == 4:
                    data.append([float(x) for x in parts])
    return np.array(data)

def interpolate_and_report(data, col2_values):
    slope_intercept_dict = {}
    for val in col2_values:
        slope_intercept_dict[val] = {'peak_GPU_temp': (0.0, 0.0), 'peak_HBM_temp': (0.0, 0.0)}
        mask = np.isclose(data[:,1], val)
        subset = data[mask]
        if subset.shape[0] < 2:
            continue  # Need at least 2 points for regression
        x = subset[:,0].reshape(-1, 1)
        for col_idx, col_name in zip([2,3], ['peak_GPU_temp', 'peak_HBM_temp']):
            y = subset[:,col_idx]
            model = LinearRegression()
            model.fit(x, y)
            y_pred = model.predict(x)
            r2 = r2_score(y, y_pred)
            slope_intercept_dict[val][col_name] = (f"{model.coef_[0]:.3f}", f"{model.intercept_:.2f}")
            print(f"Interpolation for col={val}, {col_name}:")
            print(f"  Slope: {model.coef_[0]:.6f}, Intercept: {model.intercept_:.6f}, R^2: {r2:.6f}")
    
    for key1 in slope_intercept_dict:
        # print(f"{slope_intercept_dict[key1]['peak_GPU_temp'][0]}, {slope_intercept_dict[key1]['peak_HBM_temp'][0]}")
        # print(f"{slope_intercept_dict[key1]['peak_GPU_temp'][1]}, {slope_intercept_dict[key1]['peak_HBM_temp'][1]}")
        # print("calibrate_GPU")
        print(f"calibrate_GPU :: {key1} : ({slope_intercept_dict[key1]['peak_GPU_temp'][0]}, {slope_intercept_dict[key1]['peak_GPU_temp'][1]})")
        # print("calibrate_HBM")
        print(f"calibrate_HBM :: {key1} : ({slope_intercept_dict[key1]['peak_HBM_temp'][0]}, {slope_intercept_dict[key1]['peak_HBM_temp'][1]})")
        # elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 237)):
        #     temperature_dict["3D_1GPU"] = {
        #         5.0 : (0.107, 48.2),
        #         5.6 : (0.107, 48.3),
        #         6.8024 : (0.107, 48.7)
        #     }
        

if __name__ == "__main__":
    filename = "dray_ECTC1.txt"
    data = read_data(filename)
    # col2_values = [7.0, 7.84, 9.5234]
    col2_values = [5.0, 5.6, 6.8024]
    # col2_values = [9.0, 9.4, 10.1218]
    interpolate_and_report(data, col2_values)