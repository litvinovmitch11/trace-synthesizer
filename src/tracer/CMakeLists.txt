add_library(tracer SHARED tracer.cpp)

configure_DynamoRIO_client(tracer)
use_DynamoRIO_extension(tracer drmgr)
use_DynamoRIO_extension(tracer drutil)
