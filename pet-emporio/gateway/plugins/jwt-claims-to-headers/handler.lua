-- jwt-claims-to-headers: Extract JWT claims and inject as upstream headers.
-- Runs AFTER the jwt plugin (priority 1450) has already validated the token.
-- Extracts: sub → X-User-Id, roles → X-User-Roles, tenant_id → X-Tenant-Id

local jwt_parser = require("kong.plugins.jwt.jwt_parser")

local JwtClaimsToHeaders = {
  PRIORITY = 999,
  VERSION  = "1.0",
}

function JwtClaimsToHeaders:access(conf)
  local auth = kong.request.get_header("Authorization")
  if not auth then return end

  local token = auth:match("^[Bb]earer%s+(.+)$")
  if not token then return end

  -- Token is already validated by the jwt plugin; just parse claims.
  local ok, jwt_obj = pcall(jwt_parser.new, token)
  if not ok or not jwt_obj then return end

  local claims = jwt_obj.claims
  if not claims then return end

  -- sub → X-User-Id
  if claims.sub then
    kong.service.request.set_header("X-User-Id", tostring(claims.sub))
  end

  -- roles (array) → X-User-Roles (comma-separated)
  if claims.roles then
    if type(claims.roles) == "table" then
      kong.service.request.set_header("X-User-Roles", table.concat(claims.roles, ","))
    elseif type(claims.roles) == "string" then
      kong.service.request.set_header("X-User-Roles", claims.roles)
    end
  end

  -- tenant_id → X-Tenant-Id
  if claims.tenant_id and claims.tenant_id ~= ngx.null then
    kong.service.request.set_header("X-Tenant-Id", tostring(claims.tenant_id))
  end
end

return JwtClaimsToHeaders