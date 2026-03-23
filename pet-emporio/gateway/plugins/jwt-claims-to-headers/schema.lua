return {
  name = "jwt-claims-to-headers",
  fields = {
    { protocols = require("kong.db.schema.typedefs").protocols_http },
    { config = {
        type   = "record",
        fields = {},
      }
    },
  },
}