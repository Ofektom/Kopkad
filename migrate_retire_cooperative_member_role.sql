-- Retire the cooperative_member role: migrate all such users to customer + cooperative_status=approved
UPDATE users
SET role = 'customer', cooperative_status = 'approved'
WHERE role = 'cooperative_member';
