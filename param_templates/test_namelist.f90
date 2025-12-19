! filepath: test_namelist.f90
module test_mod
  implicit none

  integer :: a = 10
  real :: b = 3.14
  logical :: c = .true.
  character(len=20) :: d = "hello"

  namelist /my_nml/ a, b, c, d

end module test_mod
