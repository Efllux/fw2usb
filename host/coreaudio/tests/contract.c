#include <CoreAudio/AudioServerPlugIn.h>
#include <CoreFoundation/CFPlugInCOM.h>
#include <assert.h>
void *FW2USBFactory(CFAllocatorRef,CFUUIDRef);
int main(void) {
    assert(!FW2USBFactory(NULL,NULL));
    AudioServerPlugInDriverRef d=FW2USBFactory(NULL,kAudioServerPlugInTypeUUID);assert(d&&*d);
    void *queried=NULL;assert((*d)->QueryInterface(d,CFUUIDGetUUIDBytes(kAudioServerPlugInDriverInterfaceUUID),&queried)==S_OK);assert(queried==d);
    AudioServerPlugInHostInterface host={0};assert(!(*d)->Initialize(d,&host));
    AudioObjectPropertyAddress a={kAudioPlugInPropertyDeviceList,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
    assert((*d)->HasProperty(d,1,0,&a));UInt32 size=99;assert(!(*d)->GetPropertyDataSize(d,1,0,&a,0,NULL,&size));assert(size==0);
    assert(!(*d)->GetPropertyData(d,1,0,&a,0,NULL,0,&size,&size));assert(size==0);
    a.mSelector=kAudioObjectPropertyClass;UInt32 cls=0;
    assert((*d)->GetPropertyData(d,1,0,&a,0,NULL,1,&size,&cls)==kAudioHardwareBadPropertySizeError);
    assert(!(*d)->GetPropertyData(d,1,0,&a,0,NULL,sizeof(cls),&size,&cls));assert(cls==kAudioPlugInClassID);
    assert((*d)->StartIO(d,2,0)==kAudioHardwareBadDeviceError);
    (*d)->Release(d);(*d)->Release(d);return 0;
}
