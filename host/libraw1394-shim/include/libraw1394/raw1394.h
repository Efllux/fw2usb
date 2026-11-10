/* Independently declared supported ABI subset; MIT OR Apache-2.0.
 * Function/type names and signatures follow libraw1394. This is not its header.
 * One handle per thread; callbacks may update generation/userdata, not reenter IO
 * or destroy the active handle. Length-bounded buffers must be valid C storage.
 */
#ifndef FW2USB_RAW1394_H
#define FW2USB_RAW1394_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct fw2usb_raw_handle *raw1394handle_t;
typedef uint16_t nodeid_t;
typedef uint64_t nodeaddr_t;
typedef uint32_t quadlet_t;
typedef uint64_t octlet_t;
struct raw1394_portinfo {int nodes;char name[32];};
typedef int (*bus_reset_handler_t)(raw1394handle_t,unsigned int);
typedef int (*raw1394_iso_recv_handler_t)(raw1394handle_t,unsigned char *,unsigned int,unsigned char,unsigned char,unsigned char,unsigned int,unsigned int);
raw1394handle_t raw1394_new_handle(void);
raw1394handle_t raw1394_new_handle_on_port(int);
void raw1394_destroy_handle(raw1394handle_t);
int raw1394_get_port_info(raw1394handle_t,struct raw1394_portinfo *,int);
int raw1394_set_port(raw1394handle_t,int);
nodeid_t raw1394_get_local_id(raw1394handle_t);
nodeid_t raw1394_get_irm_id(raw1394handle_t);
int raw1394_get_nodecount(raw1394handle_t);
unsigned int raw1394_get_generation(raw1394handle_t);
void raw1394_update_generation(raw1394handle_t,unsigned int);
void raw1394_set_userdata(raw1394handle_t,void *);
void *raw1394_get_userdata(raw1394handle_t);
bus_reset_handler_t raw1394_set_bus_reset_handler(raw1394handle_t,bus_reset_handler_t);
int raw1394_read(raw1394handle_t,nodeid_t,nodeaddr_t,size_t,quadlet_t *);
int raw1394_write(raw1394handle_t,nodeid_t,nodeaddr_t,size_t,const quadlet_t *);
int raw1394_lock(raw1394handle_t,nodeid_t,nodeaddr_t,unsigned int,quadlet_t,quadlet_t,quadlet_t *);
int raw1394_lock64(raw1394handle_t,nodeid_t,nodeaddr_t,unsigned int,octlet_t,octlet_t,octlet_t *);
int raw1394_iso_recv_init(raw1394handle_t,raw1394_iso_recv_handler_t,unsigned int,unsigned int,unsigned char,int,int);
int raw1394_iso_recv_start(raw1394handle_t,int,int,int);
void raw1394_iso_stop(raw1394handle_t);
void raw1394_iso_shutdown(raw1394handle_t);
int raw1394_loop_iterate(raw1394handle_t);
int raw1394_bandwidth_modify(raw1394handle_t,unsigned int,int);
int raw1394_channel_modify(raw1394handle_t,unsigned int,int);
int raw1394_get_fd(raw1394handle_t);
int raw1394_reset_bus(raw1394handle_t,int);
int raw1394_wake_up(raw1394handle_t);
#ifdef __cplusplus
}
#endif
#endif
