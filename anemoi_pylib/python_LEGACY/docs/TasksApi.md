# openapi_client.TasksApi

All URIs are relative to *https://anemoisoftware.com/api*

Method | HTTP request | Description
------------- | ------------- | -------------
[**tasks_delete**](TasksApi.md#tasks_delete) | **DELETE** /tasks/ | 
[**tasks_list**](TasksApi.md#tasks_list) | **GET** /tasks/ | 


# **tasks_delete**
> list[ProjectTask] tasks_delete()



Clear list of tasks

### Example

* Api Key Authentication (api_key):
```python
from __future__ import print_function
import time
import openapi_client
from openapi_client.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to https://anemoisoftware.com/api
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://anemoisoftware.com/api"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: api_key
configuration = openapi_client.Configuration(
    host = "https://anemoisoftware.com/api",
    api_key = {
        'Authorization': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Authorization'] = 'Bearer'

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.TasksApi(api_client)
    
    try:
        api_response = api_instance.tasks_delete()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling TasksApi->tasks_delete: %s\n" % e)
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**list[ProjectTask]**](ProjectTask.md)

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

# **tasks_list**
> list[ProjectTask] tasks_list()



Get list of last tasks

### Example

* Api Key Authentication (api_key):
```python
from __future__ import print_function
import time
import openapi_client
from openapi_client.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to https://anemoisoftware.com/api
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://anemoisoftware.com/api"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: api_key
configuration = openapi_client.Configuration(
    host = "https://anemoisoftware.com/api",
    api_key = {
        'Authorization': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Authorization'] = 'Bearer'

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.TasksApi(api_client)
    
    try:
        api_response = api_instance.tasks_list()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling TasksApi->tasks_list: %s\n" % e)
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**list[ProjectTask]**](ProjectTask.md)

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

