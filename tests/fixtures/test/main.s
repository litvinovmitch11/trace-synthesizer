	.file	"llvm-link"
	.text
	.globl	main                            # -- Begin function main
	.p2align	4
	.type	main,@function
main:                                   # @main
.Lfunc_begin0:
	.cfi_startproc
# %bb.0:                                # %entry
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset %rbp, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register %rbp
	movl	$0, -4(%rbp)
	movl	$5, -12(%rbp)
	movl	$123, -8(%rbp)
	movl	-12(%rbp), %eax
	cmpl	-8(%rbp), %eax
	jle	.LBB0_2
.LBB_END0_0:
.LBB0_1:                                # %if.then
	movl	$1, -4(%rbp)
	jmp	.LBB0_3
.LBB_END0_1:
.LBB0_2:                                # %if.end
	movl	$0, -4(%rbp)
.LBB_END0_2:
.LBB0_3:                                # %return
	movl	-4(%rbp), %eax
	popq	%rbp
	.cfi_def_cfa %rsp, 8
	retq
.LBB_END0_3:
.Lfunc_end0:
	.size	main, .Lfunc_end0-main
	.cfi_endproc
	.section	.llvm_bb_addr_map,"o",@llvm_bb_addr_map,.text
	.byte	5                               # version
	.short	0                               # feature
	.quad	.Lfunc_begin0                   # function address
	.byte	4                               # number of basic blocks
	.byte	0                               # BB id
	.uleb128 .Lfunc_begin0-.Lfunc_begin0
	.uleb128 .LBB_END0_0-.Lfunc_begin0
	.byte	8
	.byte	1                               # BB id
	.uleb128 .LBB0_1-.LBB_END0_0
	.uleb128 .LBB_END0_1-.LBB0_1
	.byte	0
	.byte	2                               # BB id
	.uleb128 .LBB0_2-.LBB_END0_1
	.uleb128 .LBB_END0_2-.LBB0_2
	.byte	8
	.byte	3                               # BB id
	.uleb128 .LBB0_3-.LBB_END0_2
	.uleb128 .LBB_END0_3-.LBB0_3
	.byte	1
	.text
                                        # -- End function
	.ident	"clang version 22.0.0git (git@github.com:litvinovmitch11/llvm-project.git 56905bee6e534fe1b5da9d4a7b00155a47c31f60)"
	.section	".note.GNU-stack","",@progbits
