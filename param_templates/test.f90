module test_negative_numbers_mod

use types_mod, only : r8

implicit none
private

! Test various negative number formats
integer  :: neg_int = -1
integer  :: pos_int = 42
real(r8) :: neg_float = -3.14_r8
real(r8) :: neg_sci = -1.5e-3_r8
real(r8) :: neg_big_sci = -2.0E+5_r8
integer  :: neg_zero = -0
real(r8) :: neg_small = -0.001_r8

! Test arrays with negative values
integer  :: mixed_array(3) = (/-1, 2, -3/)
real(r8) :: neg_array(2) = (/-1.0_r8, -2.5_r8/)

! Test mixed positive and negative on same line
integer  :: pos_val = 10, neg_val = -20
real(r8) :: pos_real = 1.5_r8, neg_real = -2.7_r8

namelist /test_nml/ neg_int, pos_int, neg_float, neg_sci, neg_big_sci, &
                    neg_zero, neg_small, mixed_array, neg_array, &
                    pos_val, neg_val, pos_real, neg_real

end module test_negative_numbers_mod