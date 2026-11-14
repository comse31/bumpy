components {
  id: "mesh"
  component: "/main/platforms/default/platform.mesh"
}
components {
  id: "collision_object"
  component: "/main/platforms/platform.collisionobject"
}
components {
  id: "script"
  component: "/main/platforms/platform.script"
}
components {
  id: "slope"
  component: "/main/platforms/sloped/sloped.script"
  properties {
    id: "direction"
    value: "0.0"
    type: PROPERTY_TYPE_NUMBER
  }
}
components {
  id: "sticky"
  component: "/main/platforms/sticky/sticky.script"
  properties {
    id: "sticky"
    value: "0.0"
    type: PROPERTY_TYPE_NUMBER
  }
}
