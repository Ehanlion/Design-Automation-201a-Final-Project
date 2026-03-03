# openapi_client.LibraryApi

All URIs are relative to *https://anemoisoftware.com/api*

Method | HTTP request | Description
------------- | ------------- | -------------
[**library_create**](LibraryApi.md#library_create) | **POST** /library/ | 
[**library_delete**](LibraryApi.md#library_delete) | **DELETE** /library/{libraryid}/ | 
[**library_list**](LibraryApi.md#library_list) | **GET** /library/ | 
[**library_material_create**](LibraryApi.md#library_material_create) | **POST** /library/{libraryid}/material/ | 
[**library_material_delete**](LibraryApi.md#library_material_delete) | **DELETE** /library/{libraryid}/material/{materialid}/ | 
[**library_material_list**](LibraryApi.md#library_material_list) | **GET** /library/{libraryid}/material/ | 
[**library_material_read**](LibraryApi.md#library_material_read) | **GET** /library/{libraryid}/material/{materialid}/ | 
[**library_material_update**](LibraryApi.md#library_material_update) | **PUT** /library/{libraryid}/material/{materialid}/ | 
[**library_permissions_list**](LibraryApi.md#library_permissions_list) | **GET** /library/{libraryid}/permissions/ | 
[**library_permissions_update**](LibraryApi.md#library_permissions_update) | **PUT** /library/{libraryid}/permissions/ | 
[**library_read**](LibraryApi.md#library_read) | **GET** /library/{libraryid}/ | 
[**library_update**](LibraryApi.md#library_update) | **PUT** /library/{libraryid}/ | 


# **library_create**
> Library library_create(data)



Create new library

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
    api_instance = openapi_client.LibraryApi(api_client)
    data = openapi_client.Library() # Library | 

    try:
        api_response = api_instance.library_create(data)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_create: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **data** | [**Library**](Library.md)|  | 

### Return type

[**Library**](Library.md)

### Authorization

[api_key](../README.md#api_key)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** |  |  -  |
**400** | Bad request, error returned |  -  |
**401** | Not authorized |  -  |
**403** | Not authorized |  -  |
**404** | Not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **library_delete**
> library_delete(libraryid, data)



Update a library

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
    api_instance = openapi_client.LibraryApi(api_client)
    libraryid = 'libraryid_example' # str | 
data = openapi_client.Library() # Library | 

    try:
        api_instance.library_delete(libraryid, data)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_delete: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **libraryid** | **str**|  | 
 **data** | [**Library**](Library.md)|  | 

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

# **library_list**
> list[Library] library_list()



Get list of libraries

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
    api_instance = openapi_client.LibraryApi(api_client)
    
    try:
        api_response = api_instance.library_list()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_list: %s\n" % e)
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**list[Library]**](Library.md)

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

# **library_material_create**
> Material library_material_create(libraryid, data)



Create a material

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
    api_instance = openapi_client.LibraryApi(api_client)
    libraryid = 56 # int | 
data = openapi_client.Material() # Material | 

    try:
        api_response = api_instance.library_material_create(libraryid, data)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_material_create: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **libraryid** | **int**|  | 
 **data** | [**Material**](Material.md)|  | 

### Return type

[**Material**](Material.md)

### Authorization

[api_key](../README.md#api_key)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**201** |  |  -  |
**400** | Bad request, error returned |  -  |
**401** | Not authorized |  -  |
**403** | Not authorized |  -  |
**404** | Not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **library_material_delete**
> library_material_delete(libraryid, materialid)



Delete a material

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
    api_instance = openapi_client.LibraryApi(api_client)
    libraryid = 56 # int | 
materialid = 56 # int | 

    try:
        api_instance.library_material_delete(libraryid, materialid)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_material_delete: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **libraryid** | **int**|  | 
 **materialid** | **int**|  | 

### Return type

void (empty response body)

### Authorization

[api_key](../README.md#api_key)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: Not defined

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Deleted |  -  |
**401** | Not authorized |  -  |
**403** | Not authorized |  -  |
**404** | Not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **library_material_list**
> list[Material] library_material_list(libraryid)



Get list of materials

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
    api_instance = openapi_client.LibraryApi(api_client)
    libraryid = 56 # int | 

    try:
        api_response = api_instance.library_material_list(libraryid)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_material_list: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **libraryid** | **int**|  | 

### Return type

[**list[Material]**](Material.md)

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

# **library_material_read**
> Material library_material_read(libraryid, materialid)



Get a material

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
    api_instance = openapi_client.LibraryApi(api_client)
    libraryid = 56 # int | 
materialid = 56 # int | 

    try:
        api_response = api_instance.library_material_read(libraryid, materialid)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_material_read: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **libraryid** | **int**|  | 
 **materialid** | **int**|  | 

### Return type

[**Material**](Material.md)

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

# **library_material_update**
> Material library_material_update(libraryid, library, materialid)



Update a material

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
    api_instance = openapi_client.LibraryApi(api_client)
    libraryid = 'libraryid_example' # str | 
library = 56 # int | 
materialid = 56 # int | 

    try:
        api_response = api_instance.library_material_update(libraryid, library, materialid)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_material_update: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **libraryid** | **str**|  | 
 **library** | **int**|  | 
 **materialid** | **int**|  | 

### Return type

[**Material**](Material.md)

### Authorization

[api_key](../README.md#api_key)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** |  |  -  |
**400** | Bad request, error returned |  -  |
**401** | Not authorized |  -  |
**403** | Not authorized |  -  |
**404** | Not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **library_permissions_list**
> list[LibraryPermission] library_permissions_list(libraryid)



Get library permissions

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
    api_instance = openapi_client.LibraryApi(api_client)
    libraryid = 56 # int | 

    try:
        api_response = api_instance.library_permissions_list(libraryid)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_permissions_list: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **libraryid** | **int**|  | 

### Return type

[**list[LibraryPermission]**](LibraryPermission.md)

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

# **library_permissions_update**
> list[LibraryPermission] library_permissions_update(libraryid)



Update library permissions

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
    api_instance = openapi_client.LibraryApi(api_client)
    libraryid = 56 # int | 

    try:
        api_response = api_instance.library_permissions_update(libraryid)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_permissions_update: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **libraryid** | **int**|  | 

### Return type

[**list[LibraryPermission]**](LibraryPermission.md)

### Authorization

[api_key](../README.md#api_key)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** |  |  -  |
**404** | Not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **library_read**
> Library library_read(libraryid)



Get a library

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
    api_instance = openapi_client.LibraryApi(api_client)
    libraryid = 56 # int | 

    try:
        api_response = api_instance.library_read(libraryid)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_read: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **libraryid** | **int**|  | 

### Return type

[**Library**](Library.md)

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

# **library_update**
> Library library_update(libraryid, data)



Update a library

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
    api_instance = openapi_client.LibraryApi(api_client)
    libraryid = 'libraryid_example' # str | 
data = openapi_client.Library() # Library | 

    try:
        api_response = api_instance.library_update(libraryid, data)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling LibraryApi->library_update: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **libraryid** | **str**|  | 
 **data** | [**Library**](Library.md)|  | 

### Return type

[**Library**](Library.md)

### Authorization

[api_key](../README.md#api_key)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** |  |  -  |
**400** | bad request, error returned |  -  |
**401** | Not authorized |  -  |
**403** | Not authorized |  -  |
**404** | Not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

