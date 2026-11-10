/* MIT OR Apache-2.0. Independent AudioServerPlugIn skeleton using public SDK ABI.
 * No device is published until daemon/rings/clock correlation are implemented.
 */
#include <CoreAudio/AudioServerPlugIn.h>
#include <CoreFoundation/CFPlugInCOM.h>
#include <stdatomic.h>
#include <string.h>
static AudioServerPlugInDriverInterface table;
static AudioServerPlugInDriverInterface *driver=&table;
static atomic_uint refs=1;
static ULONG AddRef(void *d) {return atomic_fetch_add_explicit(&refs,1,memory_order_relaxed)+1;}
static ULONG Release(void *d) {
    unsigned n=atomic_load_explicit(&refs,memory_order_relaxed);
    while(n>1&&!atomic_compare_exchange_weak_explicit(&refs,&n,n-1,memory_order_relaxed,memory_order_relaxed)){}
    return n>1?n-1:1; /* singleton lifetime equals the loaded bundle */
}
static HRESULT Query(void *d,REFIID uuid,LPVOID *out) {
    if(!out)return E_POINTER;*out=NULL;
    CFUUIDRef requested=CFUUIDCreateFromUUIDBytes(NULL,uuid);
    Boolean supported=CFEqual(requested,IUnknownUUID)||CFEqual(requested,kAudioServerPlugInDriverInterfaceUUID);
    CFRelease(requested);if(!supported)return E_NOINTERFACE;
    AddRef(d);*out=&driver;return S_OK;
}
static OSStatus Initialize(AudioServerPlugInDriverRef d,AudioServerPlugInHostRef host) {return d==&driver&&host?0:kAudioHardwareIllegalOperationError;}
static OSStatus Create(AudioServerPlugInDriverRef d,CFDictionaryRef description,const AudioServerPlugInClientInfo *client,AudioObjectID *out) {if(out)*out=kAudioObjectUnknown;return kAudioHardwareUnsupportedOperationError;}
static OSStatus Device(AudioServerPlugInDriverRef d,AudioObjectID id) {return kAudioHardwareBadDeviceError;}
static OSStatus Client(AudioServerPlugInDriverRef d,AudioObjectID id,const AudioServerPlugInClientInfo *client) {return kAudioHardwareBadDeviceError;}
static OSStatus Change(AudioServerPlugInDriverRef d,AudioObjectID id,UInt64 action,void *info) {return kAudioHardwareBadDeviceError;}
static Boolean Has(AudioServerPlugInDriverRef d,AudioObjectID id,pid_t client,const AudioObjectPropertyAddress *a) {
    if(d!=&driver||id!=kAudioObjectPlugInObject||!a||a->mScope!=kAudioObjectPropertyScopeGlobal||a->mElement!=kAudioObjectPropertyElementMain)return false;
    switch(a->mSelector) {
    case kAudioObjectPropertyBaseClass:case kAudioObjectPropertyClass:case kAudioObjectPropertyOwner:
    case kAudioObjectPropertyName:case kAudioObjectPropertyManufacturer:case kAudioObjectPropertyOwnedObjects:
    case kAudioPlugInPropertyBundleID:case kAudioPlugInPropertyDeviceList:return true;
    default:return false;
    }
}
static OSStatus Settable(AudioServerPlugInDriverRef d,AudioObjectID id,pid_t client,const AudioObjectPropertyAddress *a,Boolean *out) {
    if(!out)return kAudioHardwareIllegalOperationError;
    if(!Has(d,id,client,a))return kAudioHardwareUnknownPropertyError;*out=false;return 0;
}
static OSStatus PropertySize(AudioServerPlugInDriverRef d,AudioObjectID id,pid_t client,const AudioObjectPropertyAddress *a,UInt32 qs,const void *q,UInt32 *out) {
    if(!out)return kAudioHardwareIllegalOperationError;
    if(!Has(d,id,client,a))return kAudioHardwareUnknownPropertyError;
    switch(a->mSelector) {
    case kAudioPlugInPropertyDeviceList:case kAudioObjectPropertyOwnedObjects:*out=0;break;
    case kAudioObjectPropertyName:case kAudioObjectPropertyManufacturer:case kAudioPlugInPropertyBundleID:*out=sizeof(CFStringRef);break;
    default:*out=sizeof(UInt32);break;
    }return 0;
}
static OSStatus Get(AudioServerPlugInDriverRef d,AudioObjectID id,pid_t client,const AudioObjectPropertyAddress *a,UInt32 qs,const void *q,UInt32 capacity,UInt32 *outSize,void *out) {
    UInt32 size;OSStatus e=PropertySize(d,id,client,a,qs,q,&size);if(e)return e;
    if(!outSize||(size&&!out))return kAudioHardwareIllegalOperationError;
    if(capacity<size)return kAudioHardwareBadPropertySizeError;*outSize=size;if(!size)return 0;
    UInt32 value=0;CFStringRef string=NULL;
    switch(a->mSelector) {
    case kAudioObjectPropertyBaseClass:value=kAudioObjectClassID;break;
    case kAudioObjectPropertyClass:value=kAudioPlugInClassID;break;
    case kAudioObjectPropertyOwner:value=kAudioObjectUnknown;break;
    case kAudioObjectPropertyName:string=CFSTR("fw2usb skeleton");break;
    case kAudioObjectPropertyManufacturer:string=CFSTR("fw2usb development");break;
    case kAudioPlugInPropertyBundleID:string=CFSTR("org.fw2usb.AudioServerPlugIn");break;
    }
    if(string){CFRetain(string);memcpy(out,&string,sizeof(string));}else memcpy(out,&value,sizeof(value));return 0;
}
static OSStatus Set(AudioServerPlugInDriverRef d,AudioObjectID id,pid_t client,const AudioObjectPropertyAddress *a,UInt32 qs,const void *q,UInt32 size,const void *data) {return Has(d,id,client,a)?kAudioHardwareUnsupportedOperationError:kAudioHardwareUnknownPropertyError;}
static OSStatus IO(AudioServerPlugInDriverRef d,AudioObjectID id,UInt32 client) {return kAudioHardwareBadDeviceError;}
static OSStatus Zero(AudioServerPlugInDriverRef d,AudioObjectID id,UInt32 client,Float64 *sample,UInt64 *host,UInt64 *seed) {return kAudioHardwareBadDeviceError;}
static OSStatus Will(AudioServerPlugInDriverRef d,AudioObjectID id,UInt32 client,UInt32 op,Boolean *will,Boolean *inPlace) {
    if(will)*will=false;if(inPlace)*inPlace=true;return kAudioHardwareBadDeviceError;
}
static OSStatus Boundary(AudioServerPlugInDriverRef d,AudioObjectID id,UInt32 client,UInt32 op,UInt32 frames,const AudioServerPlugInIOCycleInfo *cycle) {return kAudioHardwareBadDeviceError;}
static OSStatus Do(AudioServerPlugInDriverRef d,AudioObjectID id,AudioObjectID stream,UInt32 client,UInt32 op,UInt32 frames,const AudioServerPlugInIOCycleInfo *cycle,void *main,void *secondary) {return kAudioHardwareBadDeviceError;}
static AudioServerPlugInDriverInterface table={
    ._reserved=NULL,.QueryInterface=Query,.AddRef=AddRef,.Release=Release,.Initialize=Initialize,
    .CreateDevice=Create,.DestroyDevice=Device,.AddDeviceClient=Client,.RemoveDeviceClient=Client,
    .PerformDeviceConfigurationChange=Change,.AbortDeviceConfigurationChange=Change,
    .HasProperty=Has,.IsPropertySettable=Settable,.GetPropertyDataSize=PropertySize,.GetPropertyData=Get,.SetPropertyData=Set,
    .StartIO=IO,.StopIO=IO,.GetZeroTimeStamp=Zero,.WillDoIOOperation=Will,.BeginIOOperation=Boundary,.DoIOOperation=Do,.EndIOOperation=Boundary
};
void *FW2USBFactory(CFAllocatorRef allocator,CFUUIDRef type) {
    if(!type||!CFEqual(type,kAudioServerPlugInTypeUUID))return NULL;
    AddRef(&driver);return &driver;
}
