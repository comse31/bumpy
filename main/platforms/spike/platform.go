components {
  id: "mesh"
  component: "/main/platforms/spike/platform.mesh"
}
components {
  id: "collision_object"
  component: "/main/platforms/platform.collisionobject"
}
components {
  id: "spike"
  component: "/main/platforms/spike/spike.script"
  properties {
    id: "spike"
    type: PROPERTY_TYPE_NUMBER
    value: "1"
  }
}
components {
  id: "slope"
  component: "/main/platforms/sloped/sloped.script"
  properties {
    id: "direction"
    type: PROPERTY_TYPE_NUMBER
    value: "0"
  }
}
