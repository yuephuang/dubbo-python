from dubbo.generated.Sdk import sdk_pb2
from dubbo.proxy.handlers import RpcMethodHandler


def rpc_server(method_name, func, request_deserializer=None, response_deserializer=None):
    return RpcMethodHandler.unary(
        method=func,  # 实际处理请求的方法
        method_name=method_name,  # 方法名称
        request_deserializer=request_deserializer.FromString or sdk_pb2.LawgenesisRequest.FromString,
        response_serializer=response_deserializer.SerializeToString or sdk_pb2.LawgenesisReply.SerializeToString,
    )


def rpc_client(method_name):
    return
