# danka_thermal_api.UserApi

All URIs are relative to *http://localhost:8007/api*

Method | HTTP request | Description
------------- | ------------- | -------------
[**user_list**](UserApi.md#user_list) | **GET** /user/ | 


# **user_list**
> UserLicenseInfo user_list()



Get user and license info

### Example

* Api Key Authentication (api_key):
```python
from __future__ import print_function
import time
import danka_thermal_api
from danka_thermal_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:8007/api
# See configuration.py for a list of all supported configuration parameters.
configuration = danka_thermal_api.Configuration(
    host = "http://localhost:8007/api"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: api_key
configuration = danka_thermal_api.Configuration(
    host = "http://localhost:8007/api",
    api_key = {
        'Authorization': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Authorization'] = 'Bearer'

# Enter a context with an instance of the API client
with danka_thermal_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = danka_thermal_api.UserApi(api_client)
    
    try:
        api_response = api_instance.user_list()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling UserApi->user_list: %s\n" % e)
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**UserLicenseInfo**](UserLicenseInfo.md)

### Authorization

[api_key](../README.md#api_key)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** |  |  -  |
**401** | Not authorized |  -  |
**403** | Not authorized |  -  |
**404** | Not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

