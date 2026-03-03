# danka_thermal_api.FolderApi

All URIs are relative to *http://localhost:8007/api*

Method | HTTP request | Description
------------- | ------------- | -------------
[**folder_create**](FolderApi.md#folder_create) | **POST** /folder/ | 
[**folder_delete**](FolderApi.md#folder_delete) | **DELETE** /folder/{folderid}/ | 
[**folder_list**](FolderApi.md#folder_list) | **GET** /folder/ | 
[**folder_project_list**](FolderApi.md#folder_project_list) | **GET** /folder/{folderid}/project/ | 
[**folder_project_root_list**](FolderApi.md#folder_project_root_list) | **GET** /folder/project/ | 
[**folder_read**](FolderApi.md#folder_read) | **GET** /folder/{folderid}/ | 
[**folder_shared_list**](FolderApi.md#folder_shared_list) | **GET** /folder/shared/ | 
[**folder_update**](FolderApi.md#folder_update) | **PUT** /folder/{folderid}/ | 


# **folder_create**
> Folder folder_create(data)



Create a project

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
    api_instance = danka_thermal_api.FolderApi(api_client)
    data = danka_thermal_api.Folder() # Folder | 

    try:
        api_response = api_instance.folder_create(data)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling FolderApi->folder_create: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **data** | [**Folder**](Folder.md)|  | 

### Return type

[**Folder**](Folder.md)

### Authorization

[api_key](../README.md#api_key)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** |  |  -  |
**401** | Not authorized |  -  |
**403** | Not authorized |  -  |
**404** | Not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **folder_delete**
> folder_delete(folderid, data)



Delete a Folder

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
    api_instance = danka_thermal_api.FolderApi(api_client)
    folderid = 'folderid_example' # str | 
data = danka_thermal_api.Folder() # Folder | 

    try:
        api_instance.folder_delete(folderid, data)
    except ApiException as e:
        print("Exception when calling FolderApi->folder_delete: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **folderid** | **str**|  | 
 **data** | [**Folder**](Folder.md)|  | 

### Return type

void (empty response body)

### Authorization

[api_key](../README.md#api_key)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: Not defined

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Deleted |  -  |
**401** | Not authorized |  -  |
**403** | Not authorized |  -  |
**404** | Not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **folder_list**
> list[Folder] folder_list()



Get list of Folders

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
    api_instance = danka_thermal_api.FolderApi(api_client)
    
    try:
        api_response = api_instance.folder_list()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling FolderApi->folder_list: %s\n" % e)
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**list[Folder]**](Folder.md)

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

# **folder_project_list**
> list[Project] folder_project_list(folderid)



Get list of projects in folder

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
    api_instance = danka_thermal_api.FolderApi(api_client)
    folderid = 56 # int | 

    try:
        api_response = api_instance.folder_project_list(folderid)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling FolderApi->folder_project_list: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **folderid** | **int**|  | 

### Return type

[**list[Project]**](Project.md)

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

# **folder_project_root_list**
> list[Project] folder_project_root_list()



Get list of projects in root folder

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
    api_instance = danka_thermal_api.FolderApi(api_client)
    
    try:
        api_response = api_instance.folder_project_root_list()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling FolderApi->folder_project_root_list: %s\n" % e)
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**list[Project]**](Project.md)

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

# **folder_read**
> Folder folder_read(folderid)



Get a Folder

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
    api_instance = danka_thermal_api.FolderApi(api_client)
    folderid = 56 # int | 

    try:
        api_response = api_instance.folder_read(folderid)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling FolderApi->folder_read: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **folderid** | **int**|  | 

### Return type

[**Folder**](Folder.md)

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

# **folder_shared_list**
> list[Project] folder_shared_list()



Get list of projects

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
    api_instance = danka_thermal_api.FolderApi(api_client)
    
    try:
        api_response = api_instance.folder_shared_list()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling FolderApi->folder_shared_list: %s\n" % e)
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**list[Project]**](Project.md)

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

# **folder_update**
> Folder folder_update(folderid, data)



Update a Folder

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
    api_instance = danka_thermal_api.FolderApi(api_client)
    folderid = 'folderid_example' # str | 
data = danka_thermal_api.Folder() # Folder | 

    try:
        api_response = api_instance.folder_update(folderid, data)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling FolderApi->folder_update: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **folderid** | **str**|  | 
 **data** | [**Folder**](Folder.md)|  | 

### Return type

[**Folder**](Folder.md)

### Authorization

[api_key](../README.md#api_key)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** |  |  -  |
**401** | Not authorized |  -  |
**403** | Not authorized |  -  |
**404** | Not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

