"""Local provisioning command. Run only with administrator database access."""
import getpass
from core import Service,STAGES
if __name__=='__main__':
    username=input('Named worker username: ').strip()
    print('Departments: '+', '.join(STAGES+['HES','Management']))
    department=input('Department: ').strip()
    role=input('Role (worker, hes or manager): ').strip()
    password=getpass.getpass('Individual password (at least 12 characters): ')
    confirm=getpass.getpass('Repeat password: ')
    if password!=confirm:raise SystemExit('Passwords do not match; no account created')
    Service().add_user(username,password,department,role)
    print('Named worker created. Share access through an appropriate private channel.')
