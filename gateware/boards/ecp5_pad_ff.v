// Yosys techmap rule, applied by build.py --timing to flip-flops tagged
// syn_useioff only.
//
// An ECP5 I/O cell has one set/reset shared by its input, output and tristate
// flip-flops, and nextpnr refuses to pack flip-flops whose LSR nets differ.
// Yosys, however, turns any "this bit is 0 when ..." term in front of a
// flip-flop into a synchronous reset, a different one per bit. This rule folds
// such a reset back into the D input (one LUT4) so the pad flip-flops of a
// bidirectional pin are plain D flip-flops and all three fit one I/O cell.
//
// Flip-flops with a clock enable are left alone: folding an enable would read
// Q back, and a pad flip-flop may drive nothing but its pad. Only LREQ has
// one, and it is alone in its I/O cell.
(* techmap_celltype = "TRELLIS_FF" *)
module _fw2usb_pad_ff (input CLK, input LSR, input CE, input DI, input M, output Q);
    parameter GSR = "ENABLED";
    parameter CEMUX = "1";
    parameter CLKMUX = "CLK";
    parameter LSRMUX = "LSR";
    parameter SRMODE = "LSR_OVER_CE";
    parameter REGSET = "RESET";
    parameter LSRMODE = "LSR";
    parameter _TECHMAP_CONSTMSK_LSR_ = 0;
    parameter _TECHMAP_CONSTVAL_LSR_ = 0;

    localparam plain = _TECHMAP_CONSTMSK_LSR_ && !_TECHMAP_CONSTVAL_LSR_;
    localparam skip = plain || (CEMUX == "CE") || (SRMODE != "LSR_OVER_CE") ||
                      (LSRMUX != "LSR") || (CLKMUX != "CLK");
    wire _TECHMAP_FAIL_ = skip;

    localparam value = (REGSET == "SET");
    wire d;
    // d = LSR ? value : DI, with A=DI and B=LSR.
    LUT4 #(.INIT(value ? 16'hEEEE : 16'h2222)) fold (.A(DI), .B(LSR), .C(1'b0), .D(1'b0), .Z(d));
    TRELLIS_FF #(.GSR(GSR), .CEMUX("1"), .CLKMUX(CLKMUX), .LSRMUX("LSR"), .SRMODE(SRMODE),
                 .REGSET(REGSET), .LSRMODE(LSRMODE)) _TECHMAP_REPLACE_ (.CLK(CLK), .LSR(1'b0), .DI(d), .Q(Q));
endmodule
