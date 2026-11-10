#include <libraw1394/raw1394.h>
#include <assert.h>
#include <errno.h>
int main(void) {
    raw1394handle_t h=raw1394_new_handle(); assert(h);
    int token=42;raw1394_set_userdata(h,&token);assert(raw1394_get_userdata(h)==&token);
    assert(raw1394_get_fd(h)==-1 && errno==ENOTSUP);
    assert(raw1394_read(h,0,0,4,NULL)==-1 && errno==EINVAL);
    assert(raw1394_set_port(h,1)==-1 && errno==ENODEV);
    assert(raw1394_lock64(h,0,0,2,0,0,NULL)==-1 && errno==EINVAL);
    raw1394_destroy_handle(h);raw1394_destroy_handle(NULL);return 0;
}
